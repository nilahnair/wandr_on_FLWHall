import socket
import torch
import numpy as np
import time
import json
import os
import sys
from scipy.spatial.transform import Rotation as R
import smplx
import pyrender
import trimesh
from utils.misc import cast_dict_to_numpy, cast_dict_to_tensors
from rendering.render_utils import render_motion
from aitviewer.headless import HeadlessRenderer
from aitviewer.configuration import CONFIG as C
from models.base_motion_prior import Human

# Set global random seed
torch.manual_seed(0)
torch.cuda.manual_seed(0)
np.random.seed(0)


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

# --- LOAD SMPL-X MODEL --- for rendering
smplxmodel= './data/body_models'
gender = 'female'
DEVICE = torch.device("cpu")

# Load Model
MODEL_FILE = './model_weights/wandr.ckpt'

# check if the model is loaded correctly
if os.path.exists(MODEL_FILE):
    print('Model loaded successfully')
else:
    print(f"Could not find model at {MODEL_FILE}")
    sys.exit(1)

model: Human = Human.load_from_checkpoint(MODEL_FILE)
model.eval()

def map_21_to_55(pose_21):
    pose_55 = np.zeros((55, 6))  # Initialize empty array for 55 joints
    pose_21 = pose_21.reshape(21, 6)  # Ensure pose_21 is reshaped to 21x6
    pose_55[1:22] = pose_21  # Copy the first 21 joints directly
    # Pelvis (joint 0) — estimate pelvis if necessary (e.g., midpoint between hips)
    pose_55[0] = (pose_55[1] + pose_55[2]) / 2  # Average of left_hip and right_hip

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
    viewer = pyrender.Viewer(scene, use_raymond_lighting=True, show_world_axis=True)
    return

def unity_to_smplx_rotation(quat):
    """
    Convert Unity quaternion to SMPL-X quaternion.
    Applies a -90° rotation around X.
    """
    unity_quat = R.from_quat(quat)  # Unity quaternion
    adjust_rot = R.from_euler('x', -90, degrees=True)  # Adjust to SMPL-X
    smplx_quat = adjust_rot * unity_quat  # Apply rotation
    return smplx_quat.as_quat()  # Return new quaternion

def unity_to_smplx(position):
    """
    Convert a position from Unity to Python SMPL-X coordinates.
    Unity:    (X, Y, Z)
    SMPL-X:   (X, Z, -Y)
    """
    x, y, z = position
    return np.array([x, z, -y]) #removed minus from y... not sure if correct

def quaternion_to_angle_axis(q):
    # Create rotation object from quaternion
    rotation = R.from_quat(q)

    # Extract axis-angle
    angle = rotation.magnitude()
    axis = rotation.as_rotvec()

    # Normalize axis to unit vector
    axis = axis / np.linalg.norm(axis)

    # Angle in degrees (optional, depending on your need)
    angle_degrees = np.degrees(angle)

    return axis #, angle, angle_degrees

def convert_to_unity_para(out_dict):
    #convert the axis to fit unity
    converted_quaternion = None
    for key, value in out_dict.items():
        if key == 'body_transl':
            for i in range(len(value)):
                x, y, z = value[i]
                value[i] = np.array([x, z, -y])
            x, y, z= value[i]
            value[i] = np.array([x, z, -y])
        if key == 'body_orient':
            conversion_matrix = np.array([
                                            [1,  0,  0],
                                            [0,  0, -1],
                                            [0,  1,  0]
                                        ])

            for i in range(len(value)):
                x, y, z, rx, ry, rz =value[i]
                # Convert the two 3D direction vectors
                converted_dir1 = conversion_matrix @ [x,y,z]
                converted_dir2 = conversion_matrix @ [rx,ry,rz]

                # Reconstruct rotation matrix from new direction vectors
                rotation_matrix = np.column_stack((converted_dir1, converted_dir2, np.cross(converted_dir1, converted_dir2)))
                value[i] = rotation_matrix

    return out_dict


def parse_unity_message(message):
    """Parses Unity message into a structured dictionary."""
    data = {"mouse_click": None, "body_transl": None, "body_orient": None, "body_pose": None}
    data_return = {"mouse_click": None, "body_transl": None, "body_orient": None, "body_pose": None}
    try:
        parts = message.split(";")
        if len(parts) < 4:
            print("Warning: Incomplete message received.")
            return data

        if parts[0].startswith("MouseClick:"):
            mouse_click = list(map(float, parts[0].split(":")[1].split(",")))
            tempclick = unity_to_smplx(mouse_click)
            tempclick[2] = 1.0
            data["mouse_click"] = tempclick
            data_return["mouse_click"] = mouse_click
        if parts[1].startswith("Translation:"):
            transl = list(map(float, parts[1].split(":")[1].split(",")))
            data["body_transl"] = unity_to_smplx(transl)
            data_return["body_transl"] = unity_to_smplx(transl)
        if parts[2].startswith("Orientation:"):
            orient = list(map(float, parts[2].split(":")[1].split(",")))
            orient_unity = unity_to_smplx_rotation(orient)
            print(f'orient unity: {orient_unity}')
            data_return["body_orient"] = orient_unity
            orient_euler = R.from_quat(orient_unity)
            #data["body_orient"] = quaternion_to_angle_axis(orient_euler)# trying this change
            data["body_orient"] = orient_euler.as_euler('xyz', degrees=True)
        if parts[3].startswith("Pose:"):
            pose_info = list(map(float, parts[3].split(":")[1].split(",")))
            print('printing pose')
            print(len(pose_info))
            
            euler_angles = []
            for i in range(0, len(pose_info), 4):
                quaternion = pose_info[i:i+4]
                quat_unity= quaternion #putting unity to smpl here makes the rendering crap
                r = R.from_quat(quat_unity)
                #euler = quaternion_to_angle_axis(r) # trying this change
                euler = r.as_euler('xyz', degrees=True)
                euler_angles.extend([euler])

            data["body_pose"] = euler_angles
            print(f"bodypose: {len(euler_angles)}")
            quaternions = []
            for euler in euler_angles:
                quat = R.from_euler('xyz', euler, degrees=True).as_quat()  # Convert each Euler angle to quaternion
                quaternions.extend(quat)
            print(f"quaternions: {len(quaternions)}")
            data_return["body_pose"] = quaternions
        
        print('data achieved')
        generate_smplx_model(data)
    except Exception as e:
        print(f" Error parsing Unity message: {e}")
    return data

def start_server():
    """Starts the TCP server to receive data from Unity and send modified pose back."""
    HOST, PORT = "127.0.0.1", 5005
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind((HOST, PORT))
    server.listen(1)

    print(f"Waiting for Unity on {HOST}:{PORT}...")
    conn, addr = server.accept()
    print(f"Connected to {addr}")

    previous_data = None  # To store the previous frame's processed data

    try:
        while True:
            data = conn.recv(4096).decode()
            if not data:
                continue

            parsed_data = parse_unity_message(data)
            
            if (parsed_data["mouse_click"] is not None and 
                parsed_data["body_transl"] is not None and 
                parsed_data["body_orient"] is not None and 
                parsed_data["body_pose"] is not None):
                print('loop entered')

                goal = torch.tensor([-2.5, +2.5, 1.0])[None, :].to(model.device) #torch.tensor(parsed_data["mouse_click"], dtype=torch.float32).reshape(1, 3).to(model.device)
                
                # Convert to tensors and ensure correct dimensions
                body_transl_tensor = torch.tensor(parsed_data["body_transl"], dtype=torch.float32).to(model.device).reshape(1, 1, -1) #.unsqueeze(0)  # Shape: [1, 3]
                print(f"transl: {body_transl_tensor.shape}") 
                body_orient_tensor = torch.tensor(parsed_data["body_orient"], dtype=torch.float32).to(model.device).reshape(1, 1, -1) #.unsqueeze(0)  # Shape: [1, 3]
                print(f"orient: {body_orient_tensor.shape}") 
                pose_values = np.array(parsed_data["body_pose"][1:22], dtype=np.float32)
                print(f"before convertion:{len(pose_values)}")
                body_pose_tensor = torch.tensor(pose_values, dtype=torch.float32).to(model.device).reshape(1, 1, -1) #.unsqueeze(0)  # Shape: [1, 1, 63]
                print(f"pose: {body_pose_tensor.shape}") 

                # Initialize state dictionary
                '''
                init_state_dict = {
                    "body_transl": body_transl_tensor,  # Shape: [1, 1 3]
                    "body_orient": body_orient_tensor,  # Shape: [1,1, 3]
                    "body_pose": body_pose_tensor       # Shape: [1, 1, 63]
                    }
                '''
                init_state = np.load('./deps/init_pose.npz')

                init_state = {key: init_state[key] for key in init_state.files}
                init_state = cast_dict_to_tensors(init_state, device=model.device)
                motion_duration = 6
                # Run model
                out = model.rollout(init_state, goal, n_steps=motion_duration * 30, return_smpl_joints=True, angle_format='aa')

                unityconvert= convert_to_unity_para(out)
                print('out 1 achieved')
                for key, value in unityconvert.items() :
                        print(key)
                        print(value.shape)
                        print(len(value))
                out = cast_dict_to_numpy(unityconvert)
                print('out 2 achieved')

                C.update_conf({"playback_fps": 30,
                            "auto_set_floor": True,
                            "z_up": False,
                            "smplx_models": 'data/body_models'})
                renderer = HeadlessRenderer()
                render_motion(renderer=renderer, datum=unityconvert, filename='output_test.mp4', pose_repr='6d')

                tounity= {k: unityconvert[k] for k in unityconvert.keys() & {'body_transl', 'body_orient', 'body_pose', 'joints'}}

                # Ensure a consistent order if required
                expected_order = ['body_transl', 'body_orient', 'body_pose', 'joints', 'right_wrist_intention_pelv_xy']
                tounity_ordered = {k: tounity[k] for k in expected_order if k in tounity}

                print('tounity achieved')
                print(tounity_ordered['body_pose'].shape)
                temppose = np.zeros((tounity_ordered['body_pose'].shape[0], 55, 6))
            
                # Process each pose
                for i in range(tounity_ordered['body_pose'].shape[0]):
                    temppose[i] = map_21_to_55(tounity_ordered['body_pose'][i]).reshape(55,6)  # Ensure correct shape
                print(f"Mapped output shape: {temppose.shape}")
                tounity_ordered['body_pose'] = temppose
                
                if goal == previous_data:
                    print("Frame identical to previous - skipping send")
                else:
                    for i in range(tounity_ordered['body_pose'].shape[0]):
                        out_serializable = {key: tounity_ordered[key][i].tolist() for key in tounity_ordered}
                        json_data = json.dumps(out_serializable) + "\n"
                        conn.send(json_data.encode("utf-8"))
                        previous_data = goal
                        time.sleep(1 / 30)  # Maintain ~30 FPS
                
            print("Sent to Unity:")
        

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