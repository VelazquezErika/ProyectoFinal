import sys
import os
import time
import signal
import json
import redis
import boto3
from botocore.exceptions import ClientError
import s3image

SQS_URL = os.environ.get('SQS_URL')

if not SQS_URL:
    print("Error: La variable de entorno SQS_URL no está definida", flush=True)
    sys.exit(1)

REDIS_HOST = os.environ.get('REDIS_HOST')

if not REDIS_HOST:
    print("Error: La variable de entorno REDIS_HOST no está definida", flush=True)
    sys.exit(1)

WORKER_TYPE = os.environ.get('WORKER_TYPE')

if not WORKER_TYPE:
    print("Error: La variable de entorno WORKER_TYPE no está definida", flush=True)
    sys.exit(1)


r = redis.Redis(host=REDIS_HOST, decode_responses=True)

redis_ready = False

while not redis_ready:
    try:
        if r.ping():
            print("Redis is connected", flush=True)
            redis_ready = True

    except (
        redis.exceptions.ConnectionError,
        redis.exceptions.TimeoutError
    ) as e:
        print(f"Redis connection error: {e}", flush=True)
        print("Waiting for redis", flush=True)
        time.sleep(3)

    except Exception as e:
        print(f"Waiting for redis: {e}", flush=True)
        time.sleep(3)

print("Redis is active", flush=True)


client = boto3.client('sqs', region_name='us-east-1')

run = True
stop_after_next = len(sys.argv) > 1 and sys.argv[1] == 'stop'


def handle_signal(signum, frame):
    global run
    print(f"\nSeñal {signum} recibida, deteniendo worker...", flush=True)
    run = False


signal.signal(signal.SIGINT, handle_signal)
signal.signal(signal.SIGTERM, handle_signal)


while run:

    if stop_after_next:
        run = False

    try:
        message = client.receive_message(QueueUrl=SQS_URL, WaitTimeSeconds=20)

    except ClientError as e:
        if e.response['Error']['Code'] == 'QueueDoesNotExist':
            print("The queue does not exist.", flush=True)
        else:
            print(f"ClientError: {e}", flush=True)
        time.sleep(3)
        continue

    if not (message and 'Messages' in message and message['Messages']):
        print(f"[{WORKER_TYPE}] Sin mensajes en cola", flush=True)
        continue

    # FIX: definir estas variables antes del try para que el except las tenga siempre
    receipt_handle = message['Messages'][0]['ReceiptHandle']
    filename = None

    try:
        body_raw = json.loads(message['Messages'][0]['Body'])

        # SNS envuelve el mensaje de S3 en un campo "Message" (string JSON)
        # Si viene directo de S3 no tiene esa capa
        if 'Message' in body_raw:
            body = json.loads(body_raw['Message'])
        else:
            body = body_raw

        # S3 envía un mensaje de prueba "s3:TestEvent" al configurar notificaciones.
        # No tiene la clave 'Records', hay que descartarlo sin crashear.
        if 'Event' in body and body['Event'] == 's3:TestEvent':
            print(f"[{WORKER_TYPE}] Mensaje de prueba de S3 ignorado", flush=True)
            client.delete_message(QueueUrl=SQS_URL, ReceiptHandle=receipt_handle)
            continue

        bucket_name = body['Records'][0]['s3']['bucket']['name']
        key = body['Records'][0]['s3']['object']['key']
        filename = key.split('/')[-1].strip()
        message_id = message['Messages'][0]['MessageId']

        print(f"[{WORKER_TYPE}] Procesando: {filename} (msg {message_id})", flush=True)
        r.set(f"{filename}:{WORKER_TYPE}", "en proceso")

        s3image.download_file(bucket_name, key, 'image.jpg')
        print(f"[{WORKER_TYPE}] Imagen descargada", flush=True)

        if WORKER_TYPE == "resize":
            s3image.resize_image('image.jpg', 'resize.jpg')
            output_filename = 'resize.jpg'
            output_key = f'resize/{filename}'
            print(f"[{WORKER_TYPE}] Imagen redimensionada", flush=True)

        elif WORKER_TYPE == "thumbnail":
            s3image.thumbnail_image('image.jpg', 'thumb.jpg')
            output_filename = 'thumb.jpg'
            output_key = f'thumbnail/{filename}'
            print(f"[{WORKER_TYPE}] Thumbnail creado", flush=True)

        elif WORKER_TYPE == "filter":
            s3image.gray_filter('image.jpg', 'gray.jpg')
            output_filename = 'gray.jpg'
            output_key = f'gray/{filename}'
            print(f"[{WORKER_TYPE}] Filtro gris aplicado", flush=True)

        elif WORKER_TYPE == "convert":
            s3image.convert_format('image.jpg', 'convert.png')
            output_filename = 'convert.png'
            output_key = f'convert/{filename}.png'
            print(f"[{WORKER_TYPE}] Formato convertido a PNG", flush=True)

        else:
            print(f"[{WORKER_TYPE}] WORKER_TYPE no reconocido", flush=True)
            r.set(f"{filename}:{WORKER_TYPE}", "error")
            client.delete_message(QueueUrl=SQS_URL, ReceiptHandle=receipt_handle)
            continue

        s3image.upload_file(output_filename, bucket_name, output_key, extra_args={'ACL': 'public-read'})
        print(f"[{WORKER_TYPE}] Imagen subida a S3: {output_key}", flush=True)

        r.set(f"{filename}:{WORKER_TYPE}", f"completada:{WORKER_TYPE}")
        client.delete_message(QueueUrl=SQS_URL, ReceiptHandle=receipt_handle)
        print(f"[{WORKER_TYPE}] Tarea completada y mensaje eliminado", flush=True)

    except Exception as e:
        print(f"[{WORKER_TYPE}] Error: {e}", flush=True)
        # FIX: solo intentar escribir en Redis si filename ya fue definido
        if filename:
            r.set(f"{filename}:{WORKER_TYPE}", "error")
        client.delete_message(QueueUrl=SQS_URL, ReceiptHandle=receipt_handle)

print("Worker detenido.", flush=True)