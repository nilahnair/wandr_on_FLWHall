using System.Collections.Generic;
using UnityEngine;
using System.Text;
using SimpleJSON;

public class SMPLXController : MonoBehaviour
{
    public const int NUM_JOINTS = 55;

    public MouseClick mouseClickScript;
    //public SMPLX.ModelType modelType = SMPLX.ModelType.Unknown;
    //public float[] betas = new float[SMPLX.NUM_BETAS];
    //public float[] expressions = new float[SMPLX.NUM_EXPRESSIONS];

    //public bool usePoseCorrectives = true;
    //public int poseCorrectivesQuality = 0;

    private Dictionary<string, Transform> _joints;
    private Vector3 _bodyTranslation;
    private Quaternion _bodyOrientation;
    private Vector3 _bodyGlobalRotation;
    private Vector3 _bodyLocalRotation;
    private Vector3[] _jointPositions;
    private Quaternion[] _jointRotations;

    private SkinnedMeshRenderer _smr;
    private Animator _animator; // Added reference to Animator

    public float moveSpeed = 5f;
    public float rotateSpeed = 2f;
    
    private int currentFrame = 0;
    private float frameInterval = 1f / 30f; // If data is at 30 FPS
    private float elapsedTime = 0f;


    private readonly string[] _bodyJointNames = new string[]
    {
        "pelvis", "left_hip", "right_hip", "spine1", "left_knee", "right_knee", "spine2",
        "left_ankle", "right_ankle", "spine3", "left_foot", "right_foot", "neck", "left_collar",
        "right_collar", "head", "left_shoulder", "right_shoulder", "left_elbow", "right_elbow",
        "left_wrist", "right_wrist", "jaw", "left_eye_smplhf", "right_eye_smplhf", "left_index1",
        "left_index2", "left_index3", "left_middle1", "left_middle2", "left_middle3", "left_pinky1",
        "left_pinky2", "left_pinky3", "left_ring1", "left_ring2", "left_ring3", "left_thumb1",
        "left_thumb2", "left_thumb3", "right_index1", "right_index2", "right_index3", "right_middle1",
        "right_middle2", "right_middle3", "right_pinky1", "right_pinky2", "right_pinky3", "right_ring1",
        "right_ring2", "right_ring3", "right_thumb1", "right_thumb2", "right_thumb3"
    };

    private void Awake()
    {
        _jointRotations = new Quaternion[NUM_JOINTS];
        _jointPositions = new Vector3[NUM_JOINTS];
        InitializeJoints();
        //InitializeJointTransforms(); //should this be removed?
        InitializeMeshRenderer();

        // Check and disable Animator to prevent joint override
        _animator = GetComponent<Animator>();
        if (_animator != null)
        {
            _animator.enabled = false;
            Debug.LogWarning("Animator disabled to prevent joint reset.");

        }
    }

    private void InitializeJoints()
    {
        _joints = new Dictionary<string, Transform>();
        foreach (Transform t in GetComponentsInChildren<Transform>(true))
        {
            if (System.Array.Exists(_bodyJointNames, jointName => jointName == t.name))
            {
                _joints[t.name] = t;
            }
        }
        
        Debug.Log($"Initialized {_joints.Count} joints.");
    }
    
    private void UpdatePoseData()
    {
        _bodyTranslation = transform.position;
        _bodyOrientation = transform.rotation;
        
        for (int i = 0; i < _bodyJointNames.Length; i++)
        {
            if (_joints.TryGetValue(_bodyJointNames[i], out Transform joint))
            {
                Debug.Log($"current {_bodyJointNames} joints.");
                _jointRotations[i] = joint.localRotation;
                
            }
        }
    }
	
    
    public string GetInitialPoseData()
    {
        UpdatePoseData();
        
        StringBuilder sb = new StringBuilder();
        
        sb.Append($"Translation:{_bodyTranslation.x},{_bodyTranslation.y},{_bodyTranslation.z};");
        
        sb.Append($"Orientation:{_bodyOrientation.x},{_bodyOrientation.y},{_bodyOrientation.z},{_bodyOrientation.w};");
        
        sb.Append("Pose:");
        for (int i = 0; i < _jointRotations.Length; i++)
        {
            sb.Append($"{_jointRotations[i].x},{_jointRotations[i].y},{_jointRotations[i].z},{_jointRotations[i].w}");
            if (i < _jointRotations.Length - 1)
            {
                sb.Append(",");
            }
        }
        return sb.ToString();
    }

    private void InitializeMeshRenderer()
    {
        if (_smr == null)
        {
            _smr = GetComponentInChildren<SkinnedMeshRenderer>();

            if (_smr != null)
            {
                Debug.Log($"Found SkinnedMeshRenderer: {_smr.name}");
            }
            else
            {
                Debug.LogError("No SkinnedMeshRenderer found in SMPL-X model.");
            }
        }
    }
    
    private void Start()
    {
        _jointRotations = new Quaternion[NUM_JOINTS];
        Application.targetFrameRate = 60; 
    }
    
    private void InitializeJointTransforms()
    {
        // Allocate space for joint positions and rotations
        if (_jointPositions == null)
        {
            _jointPositions = new Vector3[NUM_JOINTS];
        }

        if (_jointRotations == null)
        {
            _jointRotations = new Quaternion[NUM_JOINTS];
        }

        // Fill joint positions based on the SMPL-X joint hierarchy

        for (int i = 0; i < NUM_JOINTS; i++)
        {
            if (_joints.TryGetValue(_bodyJointNames[i], out Transform joint))
            {
                _jointPositions[i] = joint.position;
                _jointRotations[i] = joint.rotation;
            }
            else
            {
                Debug.LogWarning($"Joint {_bodyJointNames} not found in hierarchy.");
            }
        }
    }
    
    private Transform GetJointTransform(int jointIndex)
    {
    	// Ensure the index is valid
    	if (jointIndex < 0 || jointIndex >= NUM_JOINTS)
    	{
        	Debug.LogError($"Invalid joint index: {jointIndex}");
        	return null;
    	}

    	// Get the joint name based on the index
    	string jointName = _bodyJointNames[jointIndex];

    	// Try to get the transform of the joint from the hierarchy
    	if (_joints.TryGetValue(jointName, out Transform jointTransform))
    	{
        	return jointTransform;
    	}
    	else
    	{
        	Debug.LogError($"Joint '{jointName}' not found in hierarchy.");
        	return null;
    	}
    }
/*
    private void Update()
    {
        string receivedData = TCPManager.Instance.GetReceivedData();

        if (!string.IsNullOrEmpty(receivedData))
        {
            Debug.Log("Received Data");
            ProcessReceivedData(receivedData);
        }
    }
    */
    /*
    private void LateUpdate()
    {
        // Force joint updates after Unity updates transforms
        foreach (var jointName in _bodyJointNames)
        {
            if (_joints.TryGetValue(jointName, out Transform joint))
            {
                //Debug.Log($"Joint {jointName}: Position = {joint.position}, Rotation = {joint.localRotation.eulerAngles}");
            }
            else
            {
                Debug.LogWarning($"Joint {jointName} not found in hierarchy.");
            }
        }
        
    }
    */
    
    private void LateUpdate()
    {
    	string receivedData = TCPManager.Instance.GetReceivedData();
    	if (!string.IsNullOrEmpty(receivedData))
    	{
        	ProcessReceivedData(receivedData);
        	Debug.Log($"Data at frame {Time.frameCount}: {receivedData}");
    	}
    }

    private Quaternion ConvertAxisAngleToQuaternion(Vector3 axisAngle)
    {
    	float angle = axisAngle.magnitude;  // Rotation magnitude = angle in radians
    	if (angle < 0.0001f) return Quaternion.identity; // Avoid division by zero

    	return Quaternion.AngleAxis(angle * Mathf.Rad2Deg, axisAngle.normalized);
    }
    
    private Quaternion SMPLXtoUnityRotation(Quaternion smplxRot)
    {
    	Quaternion adjust = Quaternion.Euler(90, 0, 0);  // +90° rotation on X-axis
    	return adjust * smplxRot;
    }

    
    private Quaternion Convert6DToQuaternion(Vector3 dirVec1, Vector3 dirVec2)
    {
    	dirVec1.Normalize();
    	Vector3 dirVec3 = Vector3.Cross(dirVec1, dirVec2).normalized;
    	dirVec2 = Vector3.Cross(dirVec3, dirVec1); // Ensure correct orthogonality

    	Matrix4x4 rotMatrix = new Matrix4x4();
    	rotMatrix.SetColumn(0, new Vector4(dirVec1.x, dirVec1.y, dirVec1.z, 0));
    	rotMatrix.SetColumn(1, new Vector4(dirVec2.x, dirVec2.y, dirVec2.z, 0));
    	rotMatrix.SetColumn(2, new Vector4(dirVec3.x, dirVec3.y, dirVec3.z, 0));
    	rotMatrix.SetColumn(3, new Vector4(0, 0, 0, 1));

    	return rotMatrix.rotation;
    
    }
    
    private Vector3 SMPLXtoUnityPosition(Vector3 smplxPos)
    {
    	return new Vector3(smplxPos.x, -smplxPos.z, smplxPos.y);
    }

 private void ProcessReceivedData(string data)
    {
        var json = JSON.Parse(data);
        if (json == null)
        {
            Debug.LogError("Failed to parse JSON data!");
            return;
        }

        // Handle body translation
        var bodyTransl = json["body_transl"].AsArray;
        if (bodyTransl != null && bodyTransl.Count > 0)
        {
            var transl = bodyTransl[0].AsArray;
            if (transl != null && transl.Count >= 3)
            {
                //Vector3 targetTranslation = new Vector3(transl[0].AsFloat, transl[2].AsFloat, -transl[1].AsFloat);
                Vector3 targetTranslation = new Vector3(transl[0].AsFloat, transl[1].AsFloat, transl[2].AsFloat);
                transform.position = Vector3.MoveTowards(transform.position, targetTranslation, Time.deltaTime * moveSpeed);
            }
        }

        // Handle body orientation
        var bodyOrient = json["body_orient"].AsArray;
        if (bodyOrient != null && bodyOrient.Count > 0)
        {
            var orient = bodyOrient[0].AsArray;
            if (orient.Count >= 6)
            {
                Vector3 dirVec1 = new Vector3(orient[0], orient[1], orient[2]);
                Vector3 dirVec2 = new Vector3(orient[3], orient[4], orient[5]);

                Quaternion smplRotation = Convert6DToQuaternion(dirVec1, dirVec2);
                //Quaternion unityRotation = SMPLXtoUnityRotation(smplRotation);

                transform.rotation = Quaternion.Slerp(transform.rotation, smplRotation, Time.deltaTime * rotateSpeed);
            }
        }

        // Handle joint rotations
        var bodyPose = json["body_pose"].AsArray;
        if (bodyPose == null)
        {
            Debug.LogError("Body pose array is missing!");
            return;
        }

        for (int i = 0; i < NUM_JOINTS && i < bodyPose.Count; i++)
        {
            var jointPose = bodyPose[i].AsArray;
            if (jointPose.Count < 6) continue;

            Vector3 dirVec1 = new Vector3(jointPose[0], jointPose[1], jointPose[2]);
            Vector3 dirVec2 = new Vector3(jointPose[3], jointPose[4], jointPose[5]);

            Quaternion jointRotation = Convert6DToQuaternion(dirVec1, dirVec2);
            //Quaternion unityRotation = SMPLXtoUnityRotation(jointRotation);

            string jointName = _bodyJointNames[i];
            if (_joints.TryGetValue(jointName, out Transform joint))
            {
                joint.localRotation = Quaternion.Lerp(joint.localRotation, jointRotation, Time.deltaTime * rotateSpeed);
            }
        }
    }
      
}

