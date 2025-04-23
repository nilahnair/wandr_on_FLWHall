using System.Collections;
using System.Collections.Generic;
using System;
using System.IO;
using System.Text;
using UnityEngine;
using UnityEngine.UI;
using System.Threading;


public class MouseClick : MonoBehaviour
{
    public Camera playerCamera;
    private Vector3 mouseClickPosition;
    private SMPLXController smplController;
    
    void Start()
    {
        Debug.Log("This is a test");
        smplController = FindObjectOfType<SMPLXController>();
        print("Mouse click output to be expected");
    }
    void Update()
    {
        if (Input.GetMouseButtonDown(0)) // Left click
        {
            /*
            Vector3 screenPos = Input.mousePosition; // Screen coordinates
            Debug.Log($"Mouse Clicked at: {screenPos}");

            if (Camera.main == null)
            {
                Debug.LogError("No Main Camera found! Make sure your camera is tagged as 'MainCamera'.");
                return;
            }

            Ray ray = Camera.main.ScreenPointToRay(screenPos);
            Vector3 worldPos = Vector3.zero;

            if (Physics.Raycast(ray, out RaycastHit hit))
            {
                worldPos = hit.point;
                Debug.Log($"Raycast hit at: {worldPos}");
            }
            else
            {
                Debug.LogWarning("Raycast did not hit anything!");
            }
            */

            // string message = $"{screenPos.x},{screenPos.y},{worldPos.x},{worldPos.y},{worldPos.z}";
            Ray myRay= playerCamera.ScreenPointToRay(Input.mousePosition);
            RaycastHit myRaycastHit;
            
            Vector3 worldPos = Vector3.zero;
            
            if (Physics.Raycast(myRay, out myRaycastHit))
            {
            	worldPos = myRaycastHit.point;
                Debug.Log($"Raycast hit at: {worldPos}");
            }
            
            
            string smplData = smplController.GetInitialPoseData();
            Debug.Log("smplData: " + smplData);
            string message = $"MouseClick:{worldPos.x},{worldPos.y},{worldPos.z};{smplData}";

            Debug.Log("Sent: " + message);
            TCPManager.Instance.SendMessageToPython(message);
        }

        /*
        // Receive Data from Python and Move Cube
        string receivedData = TCPManager.Instance.GetReceivedData();
        if (!string.IsNullOrEmpty(receivedData))
        {
                Debug.Log("Received data: " + receivedData);
        }
        */
    }
}
