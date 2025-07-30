# SPA Routing Test Script
# Test your React app's routing after deployment

import requests
import json

# Configuration
API_BASE = "http://localhost:8000/api"
OWNER = "your-github-username"  # Replace with your GitHub username
REPO = "your-repo-name"        # Replace with your repository name

def test_spa_routing(s3_url):
    """Test SPA routing on your deployed app"""
    if not s3_url:
        print("❌ No S3 URL provided")
        return
    
    print(f"Testing SPA routing for: {s3_url}")
    print("=" * 60)
    
    # Test cases for SPA routing
    test_routes = [
        "",           # Root route
        "about",      # /about
        "contact",    # /contact
        "profile",    # /profile
        "dashboard",  # /dashboard
        "non-existent-page"  # Should still return index.html
    ]
    
    for route in test_routes:
        test_url = f"{s3_url.rstrip('/')}/{route}" if route else s3_url
        
        print(f"🔍 Testing: {test_url}")
        
        try:
            response = requests.get(test_url, timeout=10)
            
            if response.status_code == 200:
                # Check if we got HTML content (index.html)
                if 'text/html' in response.headers.get('content-type', ''):
                    if '<div id="root"' in response.text or '<div id="app"' in response.text:
                        print(f"   ✅ SUCCESS: Returns React app HTML")
                    else:
                        print(f"   ⚠️  WARNING: Returns HTML but may not be React app")
                else:
                    print(f"   ❌ FAIL: Not HTML content ({response.headers.get('content-type', 'unknown')})")
            else:
                print(f"   ❌ FAIL: HTTP {response.status_code}")
                
        except requests.exceptions.RequestException as e:
            print(f"   ❌ ERROR: {str(e)}")
        
        print()

def get_project_s3_url():
    """Get the S3 URL for your project"""
    try:
        response = requests.get(f"{API_BASE}/project/s3-info/{OWNER}/{REPO}")
        if response.status_code == 200:
            data = response.json()
            return data.get('website_url')
        else:
            print(f"Failed to get S3 info: {response.status_code}")
            return None
    except Exception as e:
        print(f"Error getting S3 info: {str(e)}")
        return None

def test_asset_loading(s3_url):
    """Test if static assets load correctly"""
    if not s3_url:
        return
    
    print("Testing static asset loading...")
    print("=" * 40)
    
    try:
        # Get the main page
        response = requests.get(s3_url)
        if response.status_code != 200:
            print("❌ Cannot access main page")
            return
        
        html_content = response.text
        
        # Look for asset references
        import re
        
        # Find CSS files
        css_files = re.findall(r'href=["\']([^"\']*\.css)["\']', html_content)
        # Find JS files  
        js_files = re.findall(r'src=["\']([^"\']*\.js)["\']', html_content)
        
        print(f"Found {len(css_files)} CSS files and {len(js_files)} JS files")
        
        # Test a few asset files
        for asset in (css_files + js_files)[:5]:  # Test first 5 assets
            if asset.startswith('./'):
                asset_url = f"{s3_url.rstrip('/')}/{asset[2:]}"
            elif asset.startswith('/'):
                asset_url = f"{s3_url.rstrip('/')}{asset}"
            else:
                asset_url = f"{s3_url.rstrip('/')}/{asset}"
            
            try:
                asset_response = requests.head(asset_url, timeout=5)
                if asset_response.status_code == 200:
                    print(f"   ✅ {asset}")
                else:
                    print(f"   ❌ {asset} (HTTP {asset_response.status_code})")
            except:
                print(f"   ❌ {asset} (Request failed)")
    
    except Exception as e:
        print(f"Error testing assets: {str(e)}")

def check_routing_configuration():
    """Check if S3 is properly configured for SPA routing"""
    print("Checking S3 SPA configuration...")
    print("=" * 40)
    
    try:
        response = requests.post(f"{API_BASE}/project/setup-s3-website")
        if response.status_code == 200:
            data = response.json()
            if data.get('success'):
                print("✅ S3 website hosting is configured")
                print(f"   Website URL: {data.get('website_url', 'Not provided')}")
            else:
                print(f"❌ S3 setup failed: {data.get('error', 'Unknown error')}")
        else:
            print(f"❌ Failed to setup S3: HTTP {response.status_code}")
    except Exception as e:
        print(f"❌ Error checking S3 config: {str(e)}")

def main():
    print("🧪 React SPA Routing Test Suite")
    print("Update OWNER and REPO variables at the top of this script")
    print()
    
    if OWNER == "your-github-username" or REPO == "your-repo-name":
        print("⚠️  Please update OWNER and REPO variables with your actual values")
        return
    
    # Step 1: Check S3 configuration
    check_routing_configuration()
    print()
    
    # Step 2: Get project URL
    s3_url = get_project_s3_url()
    if not s3_url:
        print("❌ Could not get S3 URL. Make sure your project is built and deployed.")
        return
    
    print(f"📍 Project URL: {s3_url}")
    print()
    
    # Step 3: Test SPA routing
    test_spa_routing(s3_url)
    
    # Step 4: Test asset loading
    test_asset_loading(s3_url)
    
    print("🎯 Test Summary:")
    print("If all routes return the React app HTML, your SPA routing is working!")
    print("If assets load correctly, your relative paths are working!")

if __name__ == "__main__":
    main()
