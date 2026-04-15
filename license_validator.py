import requests
from machine_id import get_machine_id

try:
    from version import CURRENT_VERSION
except ImportError:
    CURRENT_VERSION = "7.0.0"


class LicenseValidator:
    def __init__(self):
        # Remote License Server Configuration
        # TODO: Replace with your actual DigitalOcean domain after deployment
        self.license_api_url = "https://stingray-app-flk7o.ondigitalocean.app/api/v1/validate"
        
        # Fallback: Gumroad validation (optional, can be removed)
        self.use_gumroad_fallback = True
        self.gumroad_product_permalink = "rlrsql"  # Update with your permalink
        self.gumroad_api_endpoint = "https://api.gumroad.com/v2/licenses/verify"
        
        # Configuration
        self.timeout = 10  # seconds
        self.machine_id = get_machine_id()

    def verify_license(self, license_key):
        """
        Bypassed for verification/compilation (Development Mode).
        Original logic is temporarily disabled.
        """
        return True, "License Bypassed (Dev Mode)", "Developer"
    
    def _validate_with_remote_server(self, license_key):
        """
        Validate license with remote API server.
        
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
            raise  # Re-raise to trigger fallback
        except requests.exceptions.ConnectionError:
            raise  # Re-raise to trigger fallback
        except Exception as e:
            return False, f"Validation error: {str(e)}", None
    
    def _validate_with_gumroad(self, license_key):
        """
        Fallback: Validate with Gumroad API.
        
        Returns:
            tuple: (is_valid, message, customer_name)
        """
        payload = {
            "product_permalink": self.gumroad_product_permalink,
            "license_key": license_key
        }
        
        try:
            response = requests.post(
                self.gumroad_api_endpoint,
                data=payload,
                timeout=self.timeout
            )
            data = response.json()
            
            if data.get('success'):
                purchase = data.get('purchase', {})
                if not purchase.get('refunded', False):
                    # Get customer name from Gumroad
                    customer_name = purchase.get('purchaser_name') or purchase.get('email', 'Customer')
                    return True, "License validated via Gumroad!", customer_name
                else:
                    return False, "This license has been refunded.", None
            else:
                return False, "Invalid license key.", None
                
        except requests.exceptions.Timeout:
            return False, "Connection timeout. Please check your internet connection.", None
        except requests.exceptions.ConnectionError:
            return False, "Cannot connect to validation service. Check your internet.", None
        except Exception as e:
            return False, f"Gumroad validation error: {str(e)}", None
    
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
