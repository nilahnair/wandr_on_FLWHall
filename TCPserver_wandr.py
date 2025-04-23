import socket
import torch
import numpy as np
import time
import json
from scipy.spatial.transform import Rotation as R
import smplx
import pyrender
import trimesh
from models.base_motion_prior import Human
from utils.misc import cast_dict_to_numpy, cast_dict_to_tensors
from rendering.render_utils import render_motion
from aitviewer.headless import HeadlessRenderer
from aitviewer.configuration import CONFIG as C

# Set global random seed
torch.manual_seed(0)
torch.cuda.manual_seed(0)
np.random.seed(0)

smplxmodel= './data/body_models'
gender = 'female'
DEVICE = torch.device("cpu")

# Load Model
MODEL_FILE = './model_weights/wandr.ckpt'
model: Human = Human.load_from_checkpoint(MODEL_FILE)
model.eval()

smpljoints={'pelvis': 0, 'left_hip': 1, 'right_hip': 2, 'spine1': 3, 'left_knee': 4, 'right_knee': 5, 
            'spine2': 6, 'left_ankle': 7, 'right_ankle': 8, 'spine3': 9, 'left_foot': 10, 
            'right_foot': 11, 'neck': 12, 'left_collar': 13, 'right_collar': 14, 'head': 15, 
            'left_shoulder': 16, 'right_shoulder': 17, 'left_elbow': 18, 'right_elbow': 19, 
            'left_wrist': 20, 'right_wrist': 21} # 'left_hand':22, 'right_hand':23}
unityjoints={ "pelvis":0,"left_hip":1,"right_hip":2,"spine1":3,"left_knee":4,"right_knee":5,
            "spine2":6,"left_ankle":7,"right_ankle":8,"spine3":9, "left_foot":10,
            "right_foot":11,"neck":12,"left_collar":13,"right_collar":14,"head":15,
            "left_shoulder":16,"right_shoulder":17,"left_elbow":18, "right_elbow":19,
            "left_wrist":20,"right_wrist":21}
    


'''
# Load Initial Pose
init_state = np.load('./deps/init_pose.npz')
init_state = {key: init_state[key] for key in init_state.files}
init_state = cast_dict_to_tensors(init_state, device=model.device)
'''

# --- FUNCTION TO CONVERT UNITY TO SMPL-X COORDINATES ---
def convert_unity_to_smplx_quaternion(q):
    """
    Converts Unity quaternion (x, y, z, w) to SMPL-X compatible quaternion.
    Applies a 180-degree rotation around the X-axis to switch from Unity's left-handed system
    to SMPL-X's right-handed system.
    """
    unity_quat = R.from_quat([q[0], q[1], q[2], q[3]])  # (x, y, z, w)
    correction = R.from_euler('x', 180, degrees=True)  # Rotate 180° around X-axis
    corrected_quat = correction * unity_quat
    return corrected_quat.as_rotvec()  # Convert to axis-angle format



def map_21_to_55(pose_21):
    pose_55 = np.zeros((55, 6))  # Initialize empty array for 55 joints
    pose_21 = pose_21.reshape(21, 6)  # Ensure pose_21 is reshaped to 21x6
    pose_55[0:21] = pose_21  # Copy the first 21 joints directly
    #print('mapping between 21 to 55')
    #print(f'pose_21: {pose_21}')
    #print(f'pose_55: {pose_55}')
    pose_55[22] = (pose_55[16] + pose_55[17]) / 2  # Jaw (estimated between shoulders)

    # Eyes (estimated around head position)
    pose_55[23] = pose_55[15] + np.array([0.02, 0, 0, 0, 0, 0])  # left_eye_smplhf
    pose_55[24] = pose_55[15] + np.array([-0.02, 0, 0, 0, 0, 0])  # right_eye_smplhf

    # Interpolating hands using wrist as the base for both hands
    pose_55[25:40] = interpolate_fingers(pose_55[20])  # left hand
    pose_55[40:55] = interpolate_fingers(pose_55[21])  # right hand
    #print(f'final pose_55: {pose_55}')
    return pose_55

def interpolate_fingers(wrist_data):
    # Generate estimated finger positions
    finger_joints = np.zeros((15, 6))  # 5 fingers * 3 joints each = 15
    wrist_pos, wrist_rot = wrist_data[:3], wrist_data[3:]

    for i in range(15):
        weight = (i % 3) / 2.0  # 3 joints per finger, simple linear interpolation
        finger_joints[i, :3] = wrist_pos + weight * np.array([0.1, 0, 0])  # Example X translation
        finger_joints[i, 3:] = wrist_rot  # Same rotation for simplicity

    return finger_joints

def quaternion_to_angle_axis(q):
    w, x, y, z = q
    # Calculate the angle (theta)
    theta = 2 * np.arccos(w)
    
    # Calculate the axis of rotation
    sin_half_theta = np.sqrt(1 - w**2)
    
    # Avoid division by zero when sin_half_theta is very small
    if sin_half_theta < 1e-6:
        axis = np.array([1.0, 0.0, 0.0])  # Default axis (arbitrary choice)
    else:
        axis = np.array([x, y, z]) / sin_half_theta
    
    return axis

def unity_to_smplx_rotation(quat):
    """
    Convert Unity quaternion to SMPL-X quaternion.
    Applies a -90° rotation around X.
    """
    unity_quat = R.from_quat(quat)  # Unity quaternion
    adjust_rot = R.from_euler('x', -90, degrees=True)  # Adjust to SMPL-X
    smplx_quat = adjust_rot * unity_quat  # Apply rotation
    return smplx_quat.as_quat()  # Return new quaternion

def smplx_to_unity_rotation(quat):
    """
    Convert SMPL-X quaternion to Unity quaternion.
    Applies a +90° rotation around X.
    """
    smplx_quat = R.from_quat(quat)  # SMPL-X quaternion
    adjust_rot = R.from_euler('x', 90, degrees=True)  # Adjust to Unity
    unity_quat = adjust_rot * smplx_quat  # Apply rotation
    return unity_quat.as_quat()  # Return new quaternion

def unity_to_smplx(position):
    """
    Convert a position from Unity to Python SMPL-X coordinates.
    Unity:    (X, Y, Z)
    SMPL-X:   (X, Z, -Y)
    """
    x, y, z = position
    return np.array([x, z, -y]) #removed minus from y... not sure if correct

def smplx_to_unity(position):
    """
    Convert a position from Python SMPL-X to Unity coordinates.
    SMPL-X:   (X, Z, -Y)
    Unity:    (X, Y, Z)
    """
    x, z, y = position
    return np.array([x, -y, z])

def generate_smplx_model(data):
    # --- LOAD SMPL-X MODEL ---
    smplx_model = smplx.create(smplxmodel, model_type="smplx", gender=gender, use_pca=False, batch_size=1)
    print('smpl model loaded')
    # Convert to torch tensors
    body_pose = torch.tensor(np.array(data['body_pose'][1:22]), dtype=torch.float32).unsqueeze(0)  # Remove root joint
    global_orient = torch.tensor(np.array(data['body_orient']), dtype=torch.float32).unsqueeze(0)  # Root rotation
    transl = torch.tensor(np.array(data['body_transl']), dtype=torch.float32).unsqueeze(0)  # Position

    # Generate 3D mesh
    output = smplx_model(global_orient=global_orient, body_pose=body_pose, transl=transl)
    vertices = output.vertices.detach().cpu().numpy().squeeze()
    faces = smplx_model.faces

    # --- RENDER WITH PYRENDER ---
    mesh = trimesh.Trimesh(vertices, faces)
    mesh = pyrender.Mesh.from_trimesh(mesh)

    scene = pyrender.Scene()
    scene.add(mesh)

    viewer = pyrender.Viewer(scene, use_raymond_lighting=True)
    return


def parse_unity_message(message):
    """Parses Unity message into a structured dictionary."""
    data = {"mouse_click": None, "body_transl": None, "body_orient": None, "body_pose": None}

    try:
        parts = message.split(";")
        if len(parts) < 4:
            print("Warning: Incomplete message received.")
            return data

        if parts[0].startswith("MouseClick:"):
            mouse_click = list(map(float, parts[0].split(":")[1].split(",")))
            tempclick = unity_to_smplx(mouse_click)
            tempclick[2] = 1.0
            #print(f"tempclick: {tempclick}")
            data["mouse_click"] = tempclick
        if parts[1].startswith("Translation:"):
            transl = list(map(float, parts[1].split(":")[1].split(",")))
            data["body_transl"] = transl #unity_to_smplx(transl)
        if parts[2].startswith("Orientation:"):
            orient = list(map(float, parts[2].split(":")[1].split(",")))
            orient_unity = unity_to_smplx_rotation(orient)
            orient_euler = R.from_quat(orient_unity)
            data["body_orient"] = orient_euler.as_euler('xyz', degrees=True)
            #orient_unity = [-orient[0], orient[1], orient[2], -orient[3]]
            #data["body_orient"] = quaternion_to_angle_axis(orient) #converting to angle axis
            #data['body_orient'] = #convert_unity_to_smplx_quaternion(orient)
        if parts[3].startswith("Pose:"):
            pose_info = list(map(float, parts[3].split(":")[1].split(",")))
            #aa_form = []
            euler_angles = []
            for i in range(0, len(pose_info), 4):
                quaternion = pose_info[i:i+4]
                quat_unity= unity_to_smplx_rotation(quaternion)
                r = R.from_quat(quat_unity)
                euler = r.as_euler('xyz', degrees=True)
                euler_angles.extend([euler])
                #quat_unity = [-quaternion[0], quaternion[1], quaternion[2], -quaternion[3]]
                #axis_angle = quaternion_to_angle_axis(quaternion)
                #axis_angle = convert_unity_to_smplx_quaternion(quaternion)
                #aa_form.extend([axis_angle])

            #body_pose_63 = euler_angles[:63]
            #body_pose_63 = aa_form[:66]
            #pose_tensor = torch.tensor(body_pose_63, dtype=torch.float32).reshape(1, 1, -1)
            #print(f"Pose tensor shape: {pose_tensor.shape}")
            data["body_pose"] = euler_angles #aa_form
            # SMPL-X 55 to 21-joint Mapping
            # Ensure correct mapping (21 joints)
            
            # Extract only the required 21 joints

            #body_pose_21 = []
            #body_pose_21 = aa_form[:63]  # Trim or pad if necessary
            #assert len(body_pose_21) == 63, f"Expected 63 values, got {len(body_pose_21)}"
            #print(len(aa_form))
            #data["body_pose"] = aa_form #body_pose_21
        print('data achieved')
        generate_smplx_model(data)
        
            
    except Exception as e:
        print(f" Error parsing Unity message: {e}")

    return data

def sixd_to_quaternion(sixd):
    """
    Convert a 6D rotation representation to a quaternion.
    
    Args:
        sixd (numpy array): A 6D rotation representation (shape: [6] or [batch, 6])
    
    Returns:
        numpy array: Quaternion [x, y, z, w] (shape: [4] or [batch, 4])
    """
    sixd = np.array(sixd)
    batched = len(sixd.shape) > 1  # Check if input is batched

    if not batched:
        sixd = sixd.reshape(1, 6)  # Convert to batch format

    x_raw = sixd[:, :3]  # First 3D vector
    y_raw = sixd[:, 3:6]  # Second 3D vector

    # Normalize the first vector
    x = x_raw / np.linalg.norm(x_raw, axis=-1, keepdims=True)

    # Make the second vector orthogonal to the first
    y = y_raw - np.sum(y_raw * x, axis=-1, keepdims=True) * x
    y = y / np.linalg.norm(y, axis=-1, keepdims=True)

    # Compute the third vector using cross product
    z = np.cross(x, y)

    # Create the full rotation matrix
    rot_mat = np.stack([x, y, z], axis=-1)  # Shape: [batch, 3, 3]

    # Convert rotation matrix to quaternion
    quaternions = R.from_matrix(rot_mat).as_quat()  # Shape: [batch, 4]

    return quaternions if batched else quaternions[0]  # Remove batch dim if needed


def start_server():
    """Starts the TCP server to receive data from Unity and send modified pose back."""
    HOST, PORT = "127.0.0.1", 5005
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind((HOST, PORT))
    server.listen(1)

    print(f"Waiting for Unity on {HOST}:{PORT}...")
    conn, addr = server.accept()
    print(f"Connected to {addr}")

    try:
        while True:
            data = conn.recv(4096).decode()
            if not data:
                continue

            parsed_data = parse_unity_message(data)

            print(f"Mouse Click: {parsed_data['mouse_click']}")
            print(f"Body Translation: {np.shape(parsed_data['body_transl'])}")
            print(f"Body Orientation: {np.shape(parsed_data['body_orient'])}")
            print(f"Body Pose Shape: {np.shape(parsed_data['body_pose'])}")
            #print(f"Body Pose: {parsed_data['body_pose']}")
            

            if (parsed_data["mouse_click"] is not None and 
                parsed_data["body_transl"] is not None and 
                parsed_data["body_orient"] is not None and 
                parsed_data["body_pose"] is not None):

                goal = torch.tensor(parsed_data["mouse_click"], dtype=torch.float32).reshape(1, 3).to(model.device)
                #print(f"goal: {goal}")
                #goal = torch.tensor([-2.5, +2.5, 1.0])[None, :].to(model.device)

                # Convert to tensors and ensure correct dimensions
                body_transl_tensor = torch.tensor(parsed_data["body_transl"], dtype=torch.float32).to(model.device).reshape(1, 1, -1) #.unsqueeze(0)  # Shape: [1, 3]
                print(f"transl: {body_transl_tensor.shape}") 
                body_orient_tensor = torch.tensor(parsed_data["body_orient"], dtype=torch.float32).to(model.device).reshape(1, 1, -1) #.unsqueeze(0)  # Shape: [1, 6]
                print(f"orient: {body_orient_tensor.shape}") 
                body_pose_tensor = torch.tensor(parsed_data["body_pose"], dtype=torch.float32).to(model.device).reshape(1, 1, -1) #.unsqueeze(0)  # Shape: [1, num_joints, 3]
                print(f"pose: {body_pose_tensor.shape}") 

                # Initialize state dictionary
                init_state_dict = {
                    "body_transl": body_transl_tensor,  # Shape: [1, 1 3]
                    "body_orient": body_orient_tensor,  # Shape: [1,1, 3]
                    "body_pose": body_pose_tensor       # Shape: [1, 1, 63]
                    }
                #print(f"init_state_dict: {init_state_dict}")

                
                # Run model
                out = model.rollout(init_state_dict, goal, n_steps=180, return_smpl_joints=True, angle_format='aa')
                print('out 1 achieved')
                out = cast_dict_to_numpy(out)
                print('out 2 achieved')
                tounity= {k: out[k] for k in out.keys() & {'body_transl', 'body_orient', 'body_pose', 'joints'}}

                # Ensure a consistent order if required
                expected_order = ['body_transl', 'body_orient', 'body_pose', 'joints', 'right_wrist_intention_pelv_xy']
                tounity_ordered = {k: tounity[k] for k in expected_order if k in tounity}

                
                print('tounity achieved')
                print(tounity_ordered['body_pose'].shape)
                # Check what shape map_21_to_55 returns
                #sample_mapped = map_21_to_55(tounity_ordered['body_pose'][0])

                # Ensure temppose matches the mapped shape
                temppose = np.zeros((tounity_ordered['body_pose'].shape[0], 55, 6))
            
                # Process each pose
                for i in range(tounity_ordered['body_pose'].shape[0]):
                    #print(f"Processing index {i}")
                    #first from 21 to 55 joints mapping
                    temppose[i] = map_21_to_55(tounity_ordered['body_pose'][i]).reshape(55,6)  # Ensure correct shape
        
                 
                print(f"Mapped output shape: {temppose.shape}")
                tounity_ordered['body_pose'] = temppose
                # Convert NumPy arrays to lists for JSON serialization
                
                '''out_serializable = {key: tounity_ordered[key].tolist() for key in tounity_ordered}
                for key, value in out_serializable.items() :
                    print(key)
                    print(len(value))
                '''
                for i in range(tounity_ordered['body_pose'].shape[0]):
                    #print(f"Processing index {i}")
                    out_serializable = {key: tounity_ordered[key][i].tolist() for key in tounity_ordered}
                    #for key, value in out_serializable.items() :
                        #print(key)
                        #print(value)
                        #print(len(value))
                    # Send processed data back to Unity
                    json_data = json.dumps(out_serializable) + "\n"
                    #print('json_data achieved')
                    conn.send(json_data.encode("utf-8"))
                    #print("Sent to Unity:", json_data)
                    

                    time.sleep(1 / 30)  # Maintain ~30 FPS
            print("Sent to Unity:")
            
            #os.system("Xvfb :11 -screen 0 640x480x24 &")
            #os.environ['DISPLAY'] = ":11"
            #these two lines above might be needed for true headless rendering (without monitor)
            #check: https://github.com/eth-ait/aitviewer/issues/10
            C.update_conf({"playback_fps": 30,
                            "auto_set_floor": False,
                            "z_up": True,
                            "smplx_models": 'data/body_models'})
            renderer = HeadlessRenderer()
            render_motion(renderer=renderer, datum=out, filename='output.mp4', pose_repr='6d')

    except KeyboardInterrupt:
        print("\nServer shutting down manually...")

    except Exception as e:
        print(f" Error: {e}")

    finally:
        conn.close()
        server.close()
        print("Server shut down.")


if __name__ == "__main__":
    start_server()
