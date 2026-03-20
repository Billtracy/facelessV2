"""
Machine fingerprinting utility for license validation.
Generates a unique hardware ID for the current machine.
"""
import hashlib
import platform
import uuid
import subprocess


def get_machine_id():
    """
    Generate a unique, consistent machine ID based on hardware.
    
    Returns:
        str: SHA-256 hash of hardware identifiers
    """
    identifiers = []
    
    # 1. MAC Address (most reliable)
    try:
        mac = ':'.join(['{:02x}'.format((uuid.getnode() >> elements) & 0xff)
                       for elements in range(0, 2*6, 2)][::-1])
        identifiers.append(mac)
    except:
        pass
    
    # 2. Machine UUID (Windows: wmic, Linux: /etc/machine-id, Mac: system_profiler)
    try:
        if platform.system() == "Windows":
            output = subprocess.check_output("wmic csproduct get uuid", shell=True)
            machine_uuid = output.decode().split('\n')[1].strip()
            identifiers.append(machine_uuid)
        elif platform.system() == "Linux":
            with open('/etc/machine-id', 'r') as f:
                identifiers.append(f.read().strip())
        elif platform.system() == "Darwin":  # macOS
            output = subprocess.check_output("ioreg -rd1 -c IOPlatformExpertDevice | grep IOPlatformUUID", shell=True)
            machine_uuid = output.decode().split('"')[3]
            identifiers.append(machine_uuid)
    except:
        pass
    
    # 3. CPU Info (additional identifier)
    try:
        identifiers.append(platform.processor())
    except:
        pass
    
    # 4. System info as fallback
    identifiers.append(platform.system())
    identifiers.append(platform.machine())
    
    # Combine all identifiers and hash
    combined = '|'.join(filter(None, identifiers))
    machine_hash = hashlib.sha256(combined.encode()).hexdigest()
    
    return machine_hash


def get_short_machine_id():
    """
    Get a shorter version of machine ID for display purposes.
    
    Returns:
        str: First 16 characters of the machine hash
    """
    return get_machine_id()[:16]


if __name__ == "__main__":
    # Test the machine ID generation
    print(f"Full Machine ID: {get_machine_id()}")
    print(f"Short Machine ID: {get_short_machine_id()}")
