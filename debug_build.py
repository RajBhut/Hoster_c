# Build Debug Script
# Use this to test your repository validation before building

import requests
import json

# Configuration
API_BASE = "http://localhost:8000/api"
OWNER = "your-github-username"  # Replace with your GitHub username
REPO = "your-repo-name"        # Replace with your repository name

def test_repository_validation():
    
    
    print(f"Testing repository: {OWNER}/{REPO}")
    print("=" * 50)
    
  
    print("1. Checking if React project...")
    try:
        response = requests.get(f"{API_BASE}/project/check-react/{OWNER}/{REPO}")
        if response.status_code == 200:
            data = response.json()
            print(f"   ✅ React Check: {data['is_react']}")
            if data['is_react']:
                print(f"   📁 Project Path: {data['project_path'] or 'root'}")
                print(f"   🔧 Project Type: {data['details']['project_type']}")
                print(f"   📋 Has Build Script: {data['details']['has_build_script']}")
            else:
                print(f"   ❌ Not a React project: {data.get('details', 'No details')}")
        else:
            print(f"   ❌ Failed: {response.status_code}")
            print(f"   Error: {response.text}")
    except Exception as e:
        print(f"   ❌ Error: {str(e)}")
    
    print()
    
    # Test 2: Detailed validation
    print("2. Detailed validation...")
    try:
        response = requests.get(f"{API_BASE}/project/validate/{OWNER}/{REPO}")
        if response.status_code == 200:
            data = response.json()
            print(f"   ✅ Valid: {data['valid']}")
            
            if 'validation' in data:
                val = data['validation']
                print(f"   📦 Dependencies: {val['total_dependencies']}")
                print(f"   🛠️  Dev Dependencies: {val['total_dev_dependencies']}")
                print(f"   🔨 Build Script: {val['build_script']}")
                print(f"   ▶️  Start Script: {val['start_script']}")
                
                if data.get('warnings'):
                    print("   ⚠️  Warnings:")
                    for warning in data['warnings']:
                        print(f"      - {warning}")
                
                if data.get('recommendations'):
                    print("   💡 Recommendations:")
                    for rec in data['recommendations']:
                        print(f"      - {rec}")
        else:
            print(f"   ❌ Failed: {response.status_code}")
            print(f"   Error: {response.text}")
    except Exception as e:
        print(f"   ❌ Error: {str(e)}")
    
    print()
    
  
    print("3. Enhanced build readiness test...")
    try:
        response = requests.post(f"{API_BASE}/project/test-build/{OWNER}/{REPO}")
        if response.status_code == 200:
            data = response.json()
            analysis = data['analysis']
            
            print(f"   🎯 Ready to build: {data['ready_to_build']}")
            print(f"   ⚠️  Issues found: {data['issue_count']}")
            
            # File structure
            structure = analysis['file_structure']
            print(f"   📁 Has src/: {structure['has_src']}")
            print(f"   🌐 Has public/: {structure['has_public']}")
            print(f"   📄 Has index.html: {structure['has_index_html']}")
            print(f"   🔧 Entry points: {', '.join(structure['entry_points']) or 'None'}")
            
            # Package analysis
            pkg = analysis['package_analysis']
            if pkg:
                print(f"   📦 Project: {pkg['name']} v{pkg['version']}")
                print(f"   ⚛️  React version: {pkg['react_version']}")
                print(f"   🔨 Build tools: {', '.join([k for k, v in pkg['build_tools'].items() if v])}")
            
            # Issues and recommendations
            if analysis['potential_issues']:
                print("   🚨 Potential Issues:")
                for issue in analysis['potential_issues']:
                    print(f"      - {issue}")
            
            if analysis['recommendations']:
                print("   💡 Recommendations:")
                for rec in analysis['recommendations']:
                    print(f"      - {rec}")
                    
        else:
            print(f"   ❌ Failed: {response.status_code}")
            print(f"   Error: {response.text}")
    except Exception as e:
        print(f"   ❌ Error: {str(e)}")
    
    print()
    
    # Test 4: Repository structure
    print("4. Repository structure...")
    try:
        response = requests.get(f"{API_BASE}/project/repo-structure/{OWNER}/{REPO}")
        if response.status_code == 200:
            data = response.json()
            structure = data['structure']
            print(f"   📁 Files: {len(structure['files'])}")
            print(f"   📂 Directories: {len(structure['directories'])}")
            print(f"   ⚛️  React Projects: {data['total_react_projects']}")
            
            if structure['react_projects']:
                for project in structure['react_projects']:
                    print(f"      - {project['location']}")
        else:
            print(f"   ❌ Failed: {response.status_code}")
    except Exception as e:
        print(f"   ❌ Error: {str(e)}")

def common_build_issues():
    """Show common build issues and solutions"""
    print()
    print("Common Build Issues and Solutions:")
    print("=" * 50)
    
    issues = [
        {
            "issue": "No build script found",
            "solution": "Add '\"build\": \"react-scripts build\"' to scripts in package.json"
        },
        {
            "issue": "Dependencies missing",
            "solution": "Run 'npm install' locally and commit package-lock.json"
        },
        {
            "issue": "React not found",
            "solution": "Add React as a dependency: 'npm install react react-dom'"
        },
        {
            "issue": "Build command fails",
            "solution": "Check for TypeScript errors, ESLint errors, or missing env variables"
        },
        {
            "issue": "Project in subdirectory",
            "solution": "The system should auto-detect, but verify package.json is in the correct folder"
        }
    ]
    
    for i, item in enumerate(issues, 1):
        print(f"{i}. Issue: {item['issue']}")
        print(f"   Solution: {item['solution']}")
        print()

if __name__ == "__main__":
    print("Repository Build Debug Tool")
    print("Update OWNER and REPO variables at the top of this script")
    print()
    
    if OWNER == "your-github-username" or REPO == "your-repo-name":
        print("⚠️  Please update OWNER and REPO variables with your actual values")
        print()
    
    test_repository_validation()
    common_build_issues()
