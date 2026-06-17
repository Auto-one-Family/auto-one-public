import asyncio
import aiomqtt
import json
import time

async def test():
    print('Connecting to MQTT broker...')
    try:
        async with aiomqtt.Client('localhost', 1883) as client:
            print('Connected!')
            esp_id = 'MOCK_TEST001'
            topic = f'kaiser/god/esp/{esp_id}/sensor/4/data'
            payload = {
                'ts': int(time.time()),
                'esp_id': esp_id,
                'gpio': 4,
                'sensor_type': 'temperature',
                'raw': 3000,
                'value': 30.0,
                'unit': '°C',
                'raw_mode': True,
                'quality': 'good'
            }
            print(f'Publishing to: {topic}')
            print(f'Payload: {json.dumps(payload, indent=2)}')
            await client.publish(topic, json.dumps(payload), qos=1)
            print('Published!')
            await asyncio.sleep(0.5)
    except Exception as e:
        print(f'Error: {type(e).__name__}: {e}')

if __name__ == '__main__':
    asyncio.run(test())
