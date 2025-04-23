using UnityEngine;
using System.Net.Sockets;
using System.Text;
using System.Threading;

public class TCPManager : MonoBehaviour
{
    private TcpClient client;
    private NetworkStream stream;
    private Thread receiveThread;
    private bool running = true;
    private string lastReceivedData = "";

    public static TCPManager Instance; // 🔹 Singleton instance

    void Awake()
    {
        if (Instance == null)
        {
            Instance = this;
            DontDestroyOnLoad(gameObject);  // 🔹 Keeps TCPManager alive across scenes
        }
        else
        {
            Destroy(gameObject); // Prevent duplicate instances
            return;
        }
    }

    void Start()
    {
        try
        {
            client = new TcpClient("127.0.0.1", 5005);
            stream = client.GetStream();

            receiveThread = new Thread(ReceiveData);
            receiveThread.IsBackground = true;
            receiveThread.Start();
        }
        catch (System.Exception e)
        {
            Debug.LogError("TCP Error: " + e.Message);
        }
    }

    // 🔹 Any GameObject can call this to send a message
    public void SendMessageToPython(string message)
    {
        if (client == null || stream == null) return;

        byte[] data = Encoding.UTF8.GetBytes(message);
        stream.Write(data, 0, data.Length);
        Debug.Log("Sent to Python: " + message);
    }

    // 🔹 Background thread to receive data
    private void ReceiveData()
    {
        byte[] buffer = new byte[4096];
        StringBuilder dataBuffer = new StringBuilder();
        while (running)
        {
            if (stream == null) continue;

            try
            {
                /*
                int bytesRead = stream.Read(buffer, 0, buffer.Length);
                if (bytesRead > 0)
                {
                    lastReceivedData = Encoding.UTF8.GetString(buffer, 0, bytesRead);
                    Debug.Log("Received from Python: " + lastReceivedData);
                }
                */
                int bytesRead = stream.Read(buffer, 0, buffer.Length);
                if (bytesRead > 0)
                {
                    // Append received data to the buffer
                    dataBuffer.Append(Encoding.UTF8.GetString(buffer, 0, bytesRead));

                    // Process complete JSON messages (split by newline)
                    string[] messages = dataBuffer.ToString().Split('\n');
                    for (int i = 0; i < messages.Length - 1; i++)
                    {
                        lastReceivedData = messages[i]; // Process each message
                        Debug.Log("Received from Python: " + lastReceivedData);
                    }

                    // Keep the remaining incomplete data in the buffer
                    dataBuffer.Clear();
                    dataBuffer.Append(messages[messages.Length - 1]);

                }
            }
            catch (System.Exception e)
            {
                Debug.LogError("TCP Receive Error: " + e.Message);
            }
        }
    }

    // 🔹 Any GameObject can call this to get the latest received data
    public string GetReceivedData()
    {
        return lastReceivedData;
    }

    void OnDestroy()
    {
        running = false;
        receiveThread?.Abort();
        client?.Close();
    }
}
