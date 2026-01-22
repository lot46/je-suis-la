import requests
import sys
from datetime import datetime

class JeSuisLaAPITester:
    def __init__(self, base_url="https://simple-checkin.preview.emergentagent.com"):
        self.base_url = base_url
        self.token = None
        self.tests_run = 0
        self.tests_passed = 0
        self.test_results = []

    def log_test(self, name, success, details=""):
        """Log test result"""
        self.tests_run += 1
        if success:
            self.tests_passed += 1
            print(f"✅ {name} - PASSED")
        else:
            print(f"❌ {name} - FAILED: {details}")
        
        self.test_results.append({
            "name": name,
            "success": success,
            "details": details
        })

    def run_test(self, name, method, endpoint, expected_status, data=None, headers=None):
        """Run a single API test"""
        url = f"{self.base_url}/{endpoint}"
        test_headers = {'Content-Type': 'application/json'}
        
        if headers:
            test_headers.update(headers)
        
        if self.token and 'X-Session-Token' not in test_headers:
            test_headers['X-Session-Token'] = self.token

        print(f"\n🔍 Testing {name}...")
        print(f"   URL: {url}")
        print(f"   Method: {method}")
        print(f"   Headers: {test_headers}")
        if data:
            print(f"   Data: {data}")
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=test_headers, timeout=10)
            elif method == 'POST':
                response = requests.post(url, json=data, headers=test_headers, timeout=10)

            print(f"   Response Status: {response.status_code}")
            print(f"   Response Body: {response.text[:200]}...")

            success = response.status_code == expected_status
            details = f"Expected {expected_status}, got {response.status_code}"
            if not success:
                details += f" - Response: {response.text[:100]}"
            
            self.log_test(name, success, details if not success else "")
            
            return success, response.json() if success and response.text else {}

        except Exception as e:
            error_msg = f"Request failed: {str(e)}"
            self.log_test(name, False, error_msg)
            return False, {}

    def test_request_code_valid_email(self):
        """Test POST /api/auth/request-code with valid email"""
        test_email = f"test_{datetime.now().strftime('%H%M%S')}@example.com"
        success, response = self.run_test(
            "Request code with valid email",
            "POST",
            "api/auth/request-code",
            200,
            data={"email": test_email}
        )
        
        if success and 'code' in response and 'message' in response:
            if response['message'] == 'code_generated' and len(response['code']) == 6:
                self.test_email = test_email
                self.test_code = response['code']
                return True
            else:
                self.log_test("Request code response format", False, f"Invalid response format: {response}")
        return False

    def test_request_code_invalid_email(self):
        """Test POST /api/auth/request-code with invalid email"""
        success, response = self.run_test(
            "Request code with invalid email",
            "POST",
            "api/auth/request-code",
            422,  # FastAPI validation error
            data={"email": "invalid-email"}
        )
        return success

    def test_verify_code_valid(self):
        """Test POST /api/auth/verify-code with valid email and code"""
        if not hasattr(self, 'test_email') or not hasattr(self, 'test_code'):
            self.log_test("Verify code with valid credentials", False, "No valid email/code from previous test")
            return False
            
        success, response = self.run_test(
            "Verify code with valid credentials",
            "POST",
            "api/auth/verify-code",
            200,
            data={"email": self.test_email, "code": self.test_code}
        )
        
        if success and 'token' in response and 'user' in response:
            self.token = response['token']
            return True
        return False

    def test_verify_code_invalid(self):
        """Test POST /api/auth/verify-code with invalid code"""
        success, response = self.run_test(
            "Verify code with invalid code",
            "POST",
            "api/auth/verify-code",
            400,
            data={"email": "test@example.com", "code": "000000"}
        )
        return success

    def test_get_status_without_session(self):
        """Test GET /api/me/status without session token"""
        # Temporarily clear token to test without session
        temp_token = self.token
        self.token = None
        
        success, response = self.run_test(
            "Get status without session",
            "GET",
            "api/me/status",
            401,
            headers={'Content-Type': 'application/json'}  # Explicitly no session token
        )
        
        # Restore token for subsequent tests
        self.token = temp_token
        return success

    def test_get_status_with_session(self):
        """Test GET /api/me/status with valid session"""
        if not self.token:
            self.log_test("Get status with valid session", False, "No valid token from previous test")
            return False
            
        success, response = self.run_test(
            "Get status with valid session",
            "GET",
            "api/me/status",
            200,
            headers={'X-Session-Token': self.token}
        )
        return success

    def test_update_status_invalid_key(self):
        """Test POST /api/me/status with invalid status key"""
        if not self.token:
            self.log_test("Update status with invalid key", False, "No valid token")
            return False
            
        success, response = self.run_test(
            "Update status with invalid key",
            "POST",
            "api/me/status",
            400,
            data={"status_key": "INVALID_STATUS"},
            headers={'X-Session-Token': self.token}
        )
        return success

    def test_update_status_valid_keys(self):
        """Test POST /api/me/status with all valid status keys"""
        if not self.token:
            self.log_test("Update status with valid keys", False, "No valid token")
            return False
            
        valid_keys = ["OK", "NORMAL", "NOT_AVAILABLE", "NEED_CONTACT"]
        all_passed = True
        
        for key in valid_keys:
            success, response = self.run_test(
                f"Update status to {key}",
                "POST",
                "api/me/status",
                200,
                data={"status_key": key},
                headers={'X-Session-Token': self.token}
            )
            
            if success and 'status_key' in response and response['status_key'] == key:
                continue
            else:
                all_passed = False
                
        return all_passed

    def run_all_tests(self):
        """Run all backend API tests"""
        print("🚀 Starting Je suis là API Tests")
        print(f"Base URL: {self.base_url}")
        print("=" * 50)

        # Test sequence - order matters for session management
        test_methods = [
            self.test_request_code_valid_email,
            self.test_request_code_invalid_email,
            self.test_verify_code_valid,
            self.test_verify_code_invalid,
            self.test_get_status_without_session,
            self.test_get_status_with_session,
            self.test_update_status_invalid_key,
            self.test_update_status_valid_keys,
        ]

        for test_method in test_methods:
            try:
                test_method()
            except Exception as e:
                self.log_test(test_method.__name__, False, f"Test execution error: {str(e)}")

        # Print final results
        print("\n" + "=" * 50)
        print(f"📊 Test Results: {self.tests_passed}/{self.tests_run} passed")
        
        if self.tests_passed == self.tests_run:
            print("🎉 All tests passed!")
            return 0
        else:
            print("❌ Some tests failed")
            print("\nFailed tests:")
            for result in self.test_results:
                if not result['success']:
                    print(f"  - {result['name']}: {result['details']}")
            return 1

def main():
    tester = JeSuisLaAPITester()
    return tester.run_all_tests()

if __name__ == "__main__":
    sys.exit(main())