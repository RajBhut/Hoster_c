#!/usr/bin/env python3
"""
Debug Blank Page Issues for React Apps on S3
This script helps diagnose why a React app shows a blank page when deployed to S3.
"""

import requests
import json
import sys
from urllib.parse import urljoin

def check_s3_url(base_url):
    """Check if the S3 URL is accessible and analyze the content"""
    print(f"🔍 Checking S3 URL: {base_url}")
    
    try:
        response = requests.get(base_url, timeout=10)
        print(f"📊 Status Code: {response.status_code}")
        print(f"📊 Content-Type: {response.headers.get('content-type', 'unknown')}")
        print(f"📊 Content-Length: {len(response.text)} characters")
        
        if response.status_code == 200:
            content = response.text
            
            # Analyze HTML content
            analysis = {
                "has_html_tag": "<html" in content.lower(),
                "has_head_tag": "<head" in content.lower(),
                "has_body_tag": "<body" in content.lower(),
                "has_react_root": 'id="root"' in content or "id='root'" in content,
                "has_script_tags": "<script" in content.lower(),
                "has_css_links": '<link' in content.lower() and 'stylesheet' in content.lower(),
                "content_length": len(content),
                "absolute_paths": content.count('="/')
            }
            
            print("\n📋 Content Analysis:")
            for key, value in analysis.items():
                status = "✅" if value else "❌" if isinstance(value, bool) else "📊"
                print(f"  {status} {key}: {value}")
            
            print(f"\n📄 Content Preview (first 300 chars):")
            print("-" * 50)
            print(content[:300])
            if len(content) > 300:
                print("...")
            print("-" * 50)
            
            # Check for common issues
            issues = []
            if analysis["content_length"] < 100:
                issues.append("HTML content is very small - build may have failed")
            
            if not analysis["has_react_root"]:
                issues.append("No React root div found - React won't mount")
            
            if not analysis["has_script_tags"]:
                issues.append("No JavaScript files linked - React code won't load")
            
            if analysis["absolute_paths"] > 0:
                issues.append(f"Found {analysis['absolute_paths']} absolute paths - may cause 404 errors")
            
            if issues:
                print("\n⚠️  Issues Found:")
                for issue in issues:
                    print(f"  • {issue}")
            else:
                print("\n✅ No obvious issues found!")
            
            return True
            
        else:
            print(f"❌ Failed to load page: {response.status_code}")
            print(f"Response: {response.text[:200]}")
            return False
            
    except requests.RequestException as e:
        print(f"❌ Network error: {str(e)}")
        return False

def check_static_assets(base_url):
    """Check if static assets are accessible"""
    print(f"\n🎨 Checking static assets from: {base_url}")
    
    # Common static asset paths
    asset_paths = [
        "static/js/",
        "static/css/", 
        "assets/",
        "favicon.ico",
        "manifest.json"
    ]
    
    for asset_path in asset_paths:
        asset_url = urljoin(base_url, asset_path)
        try:
            response = requests.head(asset_url, timeout=5)
            if response.status_code == 200:
                print(f"  ✅ {asset_path} - accessible")
            else:
                print(f"  ❌ {asset_path} - {response.status_code}")
        except requests.RequestException:
            print(f"  ❌ {asset_path} - network error")

def main():
    if len(sys.argv) != 2:
        print("Usage: python debug_blank_page.py <S3_URL>")
        print("Example: python debug_blank_page.py https://mybucket.s3.amazonaws.com/projects/user/repo/")
        sys.exit(1)
    
    s3_url = sys.argv[1]
    
    # Ensure URL ends with /
    if not s3_url.endswith('/'):
        s3_url += '/'
    
    print("🚀 React App Blank Page Debugger")
    print("=" * 50)
    
    # Check main page
    success = check_s3_url(s3_url)
    
    if success:
        # Check static assets
        check_static_assets(s3_url)
        
        # Check specific index.html
        index_url = urljoin(s3_url, "index.html")
        if index_url != s3_url:
            print(f"\n📄 Checking index.html directly...")
            check_s3_url(index_url)
    
    print("\n" + "=" * 50)
    print("🔧 Common Solutions for Blank Page:")
    print("1. Ensure React build completed successfully")
    print("2. Check that index.html has <div id='root'></div>")
    print("3. Fix absolute paths (/ → ./) in index.html")
    print("4. Configure S3 ErrorDocument to index.html for SPA routing")
    print("5. Verify static assets are uploaded with correct paths")

if __name__ == "__main__":
    main()
