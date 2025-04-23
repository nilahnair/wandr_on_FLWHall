using System.Collections;
using System.Collections.Generic;
using uPLibrary.Networking.M2Mqtt;
using uPLibrary.Networking.M2Mqtt.Messages;
using UnityEngine;
using System;
using UnityEditor;
using System.Text;

public class MQTTManagerSensor : MonoBehaviour
{
	public string BrokerAddress = "129.217.152.1";//"gopher.phynetlab.com";
	public int BrokerPort = 8883;
	MqttClient client;
	public string clientId;
	Dictionary<string, IMQTTSubscriber> subscribers;
	UnityMainThreadDispatcher dispatcher;

	public bool IsConnected()
	{
		return client != null;
	}

	public void Connect()
	{
		if (client == null)
		{
			Debug.Log(string.Format("MQTTManager: Start MQTT Client at {0}", BrokerAddress));
			client = new MqttClient(BrokerAddress, BrokerPort, false, null, null, MqttSslProtocols.None);

			Debug.Log("Client is " + client);

			// register a callback-function (we have to implement, see below) which is called by the library when a message was received
			client.MqttMsgPublishReceived += client_MqttMsgPublishReceived;

			// use a unique id as client id, each time we start the application
			clientId = Guid.NewGuid().ToString();

			Debug.Log(string.Format("MQTTManager: Connecting MQTT Client"));
			client.Connect(clientId);
			Debug.Log("Client Id is " + clientId);


			foreach (KeyValuePair<string, IMQTTSubscriber> kvp in subscribers)
			{
				Debug.Log($"MQTTManager: Subscribe to {kvp.Key}");
				client.Subscribe(new string[] { kvp.Key }, new byte[] { MqttMsgBase.QOS_LEVEL_AT_MOST_ONCE });
			}
		}
	}

	public void Disconnect()
	{
		if (client != null)
		{
			Debug.Log(string.Format("MQTTManager: Disconnect MQTT Client at {0}", BrokerAddress));
			client.Disconnect();
			client = null;
			clientId = "";
		}
	}

	public void Publish(string topic, string message)
	{
		client.Publish(topic, Encoding.UTF8.GetBytes(message));
	}

	public void Publish(string topic, byte[] message)
	{
		client.Publish(topic, message);
	}

	public void Subscribe(string topic, IMQTTSubscriber subscriber)
	{
		Debug.Log($"MQTTManager: Subscription to {topic}", gameObject);
		if (subscribers == null)
		{
			subscribers = new Dictionary<string, IMQTTSubscriber>();
		}
		subscribers.Add(topic, subscriber);
		if (client != null)
		{
			client.Subscribe(new string[] { topic }, new byte[] { MqttMsgBase.QOS_LEVEL_AT_MOST_ONCE });
		}
	}

	void client_MqttMsgPublishReceived(object sender, MqttMsgPublishEventArgs e)
	{
		string msg = Encoding.UTF8.GetString(e.Message);
		string topic = e.Topic;
		dispatcher.Enqueue(() =>
		{
			//Debug.Log($"MQTTManager: Received message for {topic}", gameObject);
			if (subscribers.ContainsKey(topic))
			{
				subscribers[topic].Receive(topic, msg);
			}
		});
	}


	// Start is called before the first frame update
	void Start()
	{
		dispatcher = GetComponent<UnityMainThreadDispatcher>();
		if (subscribers == null)
		{
			subscribers = new Dictionary<string, IMQTTSubscriber>();
		}
	}

	// Update is called once per frame
	void Update()
	{

	}

	void OnDisable()
	{
		Disconnect();
	}
}

[CustomEditor(typeof(MQTTManagerSensor))]
public class MQTTManagerEditor : Editor
{
	public override void OnInspectorGUI()
	{
		DrawDefaultInspector();

		MQTTManagerSensor m = (MQTTManagerSensor)target;
		if (GUILayout.Button("Connect"))
		{
			m.Connect();
		}

		if (GUILayout.Button("Disconnect"))
		{
			m.Disconnect();
		}
	}
}
