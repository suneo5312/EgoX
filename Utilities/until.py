import json
import os
from google.protobuf.message import Message
from google.protobuf import json_format, message
from Crypto.Cipher import AES
from Configuration.AESConfiguration import MAIN_KEY, MAIN_IV

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Load accounts from JSON file
def load_accounts():
    try:
        path = os.environ.get("ACCOUNT_CONFIG", os.path.join(BASE_DIR, "Configuration", "AccountConfiguration.json"))
        with open(path, 'r') as file:
            return json.load(file)
    except FileNotFoundError:
        raise Exception("AccountConfiguration.json file not found")
    except json.JSONDecodeError:
        raise Exception("Error parsing AccountConfiguration.json")

# Load guest account bank for the like system (1 like per guest per target)
def load_guest_accounts():
    try:
        path = os.environ.get("GUEST_CONFIG", os.path.join(BASE_DIR, "Configuration", "GuestAccounts.json"))
        with open(path, 'r') as file:
            return json.load(file)
    except FileNotFoundError:
        raise Exception("GuestAccounts.json file not found - extract guest accounts via FFTool.apk")
    except json.JSONDecodeError:
        raise Exception("Error parsing GuestAccounts.json")

def save_guest_accounts(bank):
    path = os.environ.get("GUEST_CONFIG", os.path.join(BASE_DIR, "Configuration", "GuestAccounts.json"))
    with open(path, 'w') as file:
        json.dump(bank, file, indent=4)

# Track which guests already liked which target (permanent, 1 like per guest per target)
def load_usage_history():
    try:
        path = os.environ.get("USAGE_CONFIG", os.path.join(BASE_DIR, "Configuration", "UsageHistory.json"))
        with open(path, 'r') as file:
            return json.load(file)
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError:
        return {}

def save_usage_history(usage):
    path = os.environ.get("USAGE_CONFIG", os.path.join(BASE_DIR, "Configuration", "UsageHistory.json"))
    with open(path, 'w') as file:
        json.dump(usage, file, indent=2)

def pad(text: bytes) -> bytes:
    padding_length = AES.block_size - (len(text) % AES.block_size)
    return text + bytes([padding_length] * padding_length)

def aes_cbc_encrypt(text: bytes) -> bytes:
    aes = AES.new(MAIN_KEY, AES.MODE_CBC, MAIN_IV)
    return aes.encrypt(pad(text))
    
def encode_protobuf(data: dict, proto_message: Message) -> bytes:
    """
    Utility function to convert dictionary/data to proto bytes
    
    Args:
        data (dict): Dictionary with proto data
        proto_message (Message): Proto message instance
    
    Returns:
        bytes: Serialized proto data
    
    Raises:
        ValueError: If input is invalid
        Exception: If proto conversion fails
    """
    if not isinstance(data, dict):
        raise ValueError("Data must be a dictionary")
    
    if not isinstance(proto_message, Message):
        raise ValueError("proto_message must be a protobuf Message")
    
    try:
        json_format.ParseDict(data, proto_message)
        return aes_cbc_encrypt(proto_message.SerializeToString())
    except Exception as e:
        raise Exception(f"Proto conversion failed: {str(e)}")

def decode_protobuf(encoded_data: bytes, message_type: message.Message) -> message.Message:
    instance = message_type()
    instance.ParseFromString(encoded_data)
    return json.loads(json_format.MessageToJson(instance))
    