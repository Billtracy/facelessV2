# License Server Configuration

## Important: Update Before First Build

Before deploying your app to customers, you MUST update the license server URL in `license_validator.py`:

```python
# Line 13 in license_validator.py
self.license_api_url = "https://your-license-server.com/api/v1/validate"
```

Replace `https://your-license-server.com` with your actual DigitalOcean domain.

## API Specification

Your license server must implement this endpoint:

### POST /api/v1/validate

**Request:**
```json
{
  "license_key": "FCG-XXXX-XXXX-XXXX",
  "machine_id": "a1b2c3d4e5f6g7h8...",
  "app_version": "7.0.0"
}
```

**Response (Success):**
```json
{
  "valid": true,
  "message": "License validated successfully!",
  "customer_name": "John Doe"
}
```

**Response (Failure):**
```json
{
  "valid": false,
  "message": "Invalid license key"
}
```

## Fallback Behavior

The app is configured with Gumroad fallback enabled by default:

- **Primary:** Tries your license server first
- **Fallback:** If server is unreachable, tries Gumroad API
- **Disable Fallback:** Set `self.use_gumroad_fallback = False` in `license_validator.py`

## Machine Fingerprinting

The app generates a unique hardware ID for each machine:
- Based on: MAC address, system UUID, CPU info
- Prevents license key sharing
- Same machine always gets the same ID
- View with: `python machine_id.py`

## Testing Locally

Before deploying:

1. Run the test script:
   ```bash
   python license_validator.py
   ```

2. It will show your machine ID and prompt for a test key

3. Test different scenarios:
   - Valid key (will fail until server is deployed)
   - Invalid key
   - Network error (disconnect internet)

## Next Steps

After updating the URL:
1. Deploy your license server to DigitalOcean
2. Test validation with a real key
3. Update BUILD_INSTRUCTIONS.md with the new setup
4. Build and distribute your app
