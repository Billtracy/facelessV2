import requests
from machine_id import get_machine_id

try:
    from version import CURRENT_VERSION
except ImportError:
    CURRENT_VERSION = "7.0.0"


class LicenseValidator:
    def __init__(self):
        # Remote License Server (single source of truth)
        self.license_api_url = "https://licenser.mooo.com/api/v1/validate"

        # Configuration
        self.timeout = 10  # seconds
        self.machine_id = get_machine_id()

    def verify_license(self, license_key):
        """
        Validate a license key against the remote license server.

        Returns:
            tuple: (is_valid, message, customer_name)
        """
        if not license_key or not str(license_key).strip():
            return False, "Please enter a license key.", None

        return self._validate_with_remote_server(str(license_key).strip())

    def _validate_with_remote_server(self, license_key):
        """
        Validate license with the remote API server.

        Returns:
            tuple: (is_valid, message, customer_name)
        """
        payload = {
            "license_key": license_key,
            "machine_id": self.machine_id,
            "app_version": CURRENT_VERSION
        }

        try:
            response = requests.post(
                self.license_api_url,
                json=payload,
                timeout=self.timeout,
                headers={"Content-Type": "application/json"}
            )

            # Handle HTTP errors
            if response.status_code == 404:
                return False, "License server not found. Please contact support.", None
            elif response.status_code == 429:
                return False, "Too many validation attempts. Please try again later.", None
            elif response.status_code >= 500:
                return False, "License server error. Please try again later.", None

            data = response.json()

            # Check validation result
            if data.get('valid'):
                customer_name = data.get('customer_name', 'Customer')
                message = data.get('message', 'License validated successfully!')
                return True, message, customer_name
            else:
                message = data.get('message', 'Invalid license key.')
                return False, message, None

        except requests.exceptions.Timeout:
            return False, "Connection timeout. Please check your internet connection.", None
        except requests.exceptions.ConnectionError:
            return False, "Cannot connect to the license server. Check your internet.", None
        except Exception as e:
            return False, f"Validation error: {str(e)}", None

    def get_machine_id_display(self):
        """
        Get a shortened machine ID for display purposes.

        Returns:
            str: First 16 characters of machine hash
        """
        return self.machine_id[:16]


# For testing
if __name__ == "__main__":
    validator = LicenseValidator()
    print(f"Machine ID: {validator.get_machine_id_display()}")

    # Test validation
    test_key = input("Enter license key to test: ")
    is_valid, message, customer_name = validator.verify_license(test_key)
    print(f"Valid: {is_valid}")
    print(f"Message: {message}")
    if customer_name:
        print(f"Customer: {customer_name}")
