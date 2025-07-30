#!/usr/bin/env python3
"""
Test Node.js Version Compatibility for React Builds
This script helps verify if a React project will build successfully with different Node versions.
"""

import json
import os
import sys

def check_vite_compatibility(package_json_path):
    """Check if Vite version is compatible with Node.js versions"""
    if not os.path.exists(package_json_path):
        print(f"❌ package.json not found at {package_json_path}")
        return False
    
    try:
        with open(package_json_path, 'r') as f:
            package_data = json.load(f)
        
        dependencies = package_data.get('dependencies', {})
        dev_dependencies = package_data.get('devDependencies', {})
        
        # Check Vite version
        vite_version = dev_dependencies.get('vite', dependencies.get('vite', None))
        
        print("🔍 Node.js Compatibility Check")
        print("=" * 40)
        
        if vite_version:
            print(f"📦 Vite version: {vite_version}")
            
            # Check version compatibility
            if any(v in vite_version for v in ['7.', '^7', '~7']):
                print("⚠️  Vite 7.x detected - Requires Node.js 20+ or 22+")
                print("🔧 Recommended: Use Node.js 20.19.0 or higher")
                print("🐳 Docker: Use 'node:20-alpine' or 'node:22-alpine'")
                
                # Check if engines field exists
                engines = package_data.get('engines', {})
                if 'node' in engines:
                    print(f"✅ Node engine requirement found: {engines['node']}")
                else:
                    print("⚠️  No Node engine requirement specified")
                    print("💡 Consider adding: \"engines\": {\"node\": \">=20.0.0\"}")
                
            elif any(v in vite_version for v in ['6.', '^6', '~6']):
                print("✅ Vite 6.x detected - Compatible with Node.js 18+")
                print("🐳 Docker: 'node:18-alpine' or higher works")
                
            elif any(v in vite_version for v in ['5.', '^5', '~5', '4.', '^4', '~4']):
                print("✅ Vite 4.x/5.x detected - Compatible with Node.js 16+")
                print("🐳 Docker: 'node:16-alpine' or higher works")
            
        else:
            print("📦 No Vite found - checking for other build tools...")
            
            # Check for Create React App
            if 'react-scripts' in dependencies or 'react-scripts' in dev_dependencies:
                react_scripts_version = dependencies.get('react-scripts', dev_dependencies.get('react-scripts', ''))
                print(f"📦 Create React App detected: {react_scripts_version}")
                print("✅ Generally compatible with Node.js 16+")
                print("🐳 Docker: 'node:18-alpine' recommended")
            
            # Check for Next.js
            if 'next' in dependencies:
                next_version = dependencies.get('next', '')
                print(f"📦 Next.js detected: {next_version}")
                print("✅ Check Next.js docs for Node compatibility")
        
        # Check React version
        react_version = dependencies.get('react', '')
        if react_version:
            print(f"⚛️  React version: {react_version}")
            if any(v in react_version for v in ['19.', '^19', '~19']):
                print("💡 React 19.x - Latest version, ensure all tools are compatible")
            elif any(v in react_version for v in ['18.', '^18', '~18']):
                print("✅ React 18.x - Stable and widely supported")
        
        print("\n" + "=" * 40)
        print("🚀 Build Recommendations:")
        
        if vite_version and any(v in vite_version for v in ['7.', '^7']):
            print("1. Use Node.js 20+ in Docker container")
            print("2. Update package.json engines field")
            print("3. Consider downgrading Vite if Node upgrade isn't possible")
        else:
            print("1. Current setup should work with Node.js 18+")
            print("2. Ensure Docker uses compatible Node version")
        
        print("4. Clear npm cache if build issues persist")
        print("5. Check for conflicting dependencies")
        
        return True
        
    except Exception as e:
        print(f"❌ Error reading package.json: {str(e)}")
        return False

def suggest_fixes(package_json_path):
    """Suggest fixes for common compatibility issues"""
    print("\n🔧 Suggested Fixes:")
    print("-" * 20)
    
    print("1. Update Docker Node version:")
    print("   FROM: node:18-alpine")
    print("   TO:   node:20-alpine")
    
    print("\n2. Add .npmrc file:")
    print("   legacy-peer-deps=true")
    print("   fund=false")
    
    print("\n3. Update package.json engines:")
    print('   "engines": {')
    print('     "node": ">=20.0.0"')
    print('   }')
    
    print("\n4. Alternative: Downgrade Vite:")
    print("   npm install vite@^5.4.0 --save-dev")

def main():
    if len(sys.argv) != 2:
        print("Usage: python check_node_compatibility.py <path_to_package.json>")
        print("Example: python check_node_compatibility.py ./package.json")
        sys.exit(1)
    
    package_json_path = sys.argv[1]
    
    if check_vite_compatibility(package_json_path):
        suggest_fixes(package_json_path)

if __name__ == "__main__":
    main()
