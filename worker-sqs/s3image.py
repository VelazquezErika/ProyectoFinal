import logging
import boto3
from botocore.exceptions import ClientError
import os


def upload_file(file_name, bucket, object_name=None, extra_args = {}):
    """Upload a file to an S3 bucket

    :param file_name: File to upload
    :param bucket: Bucket to upload to
    :param object_name: S3 object name. If not specified then file_name is used
    :return: True if file was uploaded, else False
    """


    if object_name is None:
        object_name = os.path.basename(file_name)


    s3_client = boto3.client('s3')

    try:
        response = s3_client.upload_file(file_name, bucket, object_name, ExtraArgs=extra_args)
    except ClientError as e:
        logging.error(e)
        return False
    return True
    
    
def download_file(bucket, key , file_name):
    s3 = boto3.client('s3')
    print(bucket)
    s3.download_file(Bucket=bucket, Key=key, Filename= file_name)
  
   
def resize_image(file_name, new_name):
    from PIL import Image
    im = Image.open(file_name)
    resized_im = im.resize((round(im.size[0]*0.5), round(im.size[1]*0.5)))
    resized_im.save(new_name)


def thumbnail_image(file_name, new_name):
    from PIL import Image
    im = Image.open(file_name)
    im.thumbnail((128, 128))
    im.save(new_name)


def gray_filter(file_name, new_name):
    from PIL import Image
    im = Image.open(file_name)
    gray_im = im.convert("L")
    gray_im.save(new_name)


def convert_format(file_name, new_name):
    from PIL import Image
    im = Image.open(file_name)
    im.save(new_name)