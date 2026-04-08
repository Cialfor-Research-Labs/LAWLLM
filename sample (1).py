import boto3

bedrock = boto3.client(
    'bedrock-runtime',
    region_name='ap-south-1',
    aws_access_key_id='AKIAVUMCTST2EZTBWJFD',  # Your access key
    aws_secret_access_key='oeJv6+xA2VPg4agXurqYrq8W5M5J53N04wDU3LRf'    # Your secret key
)

try:
    response = bedrock.converse(
        modelId="mistral.ministral-3-14b-instruct",
        messages=[{"role": "user", "content": [{"text": "Explain section 66F of IT ACT 2000"}]}],
        inferenceConfig={"maxTokens": 800}
    )
    print("✅ Working!")
    print(response['output']['message']['content'][0]['text'])
except Exception as e:
    print(f"❌ Error: {e}")