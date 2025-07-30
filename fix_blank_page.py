#!/usr/bin/env python3
"""
Quick Fix for React Blank Page Issues
This script attempts to fix common issues that cause blank pages in deployed React apps.
"""

import os
import sys
import re
import json
from pathlib import Path

def fix_index_html(file_path):
    """Fix common index.html issues that cause blank pages"""
    print(f"🔧 Fixing {file_path}...")
    
    if not os.path.exists(file_path):
        print(f"❌ File not found: {file_path}")
        return False
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        original_content = content
        changes = []
        
        # 1. Fix absolute paths
        pattern = r'(src|href)="(/[^"]*?)"'
        def fix_path(match):
            attr, path = match.groups()
            # Don't fix external URLs
            if path.startswith(('http', 'https', 'data:', 'mailto:', 'tel:')):
                return match.group(0)
            return f'{attr}=".{path}"'
        
        new_content = re.sub(pattern, fix_path, content)
        if new_content != content:
            content = new_content
            changes.append("Fixed absolute paths to relative")
        
        # 2. Fix base href
        if '<base href="/">' in content:
            content = content.replace('<base href="/">', '<base href="./">')
            changes.append("Fixed base href to relative")
        elif '<head>' in content and '<base href="./">' not in content:
            content = content.replace('<head>', '<head>\n    <base href="./">')
            changes.append("Added relative base href")
        
        # 3. Ensure React root div exists
        if 'id="root"' not in content and "id='root'" not in content:
            if '<body>' in content:
                content = content.replace('<body>', '<body>\n    <div id="root"></div>')
                changes.append("Added React root div")
        
        # 4. Add viewport meta tag if missing
        if 'viewport' not in content and '<head>' in content:
            viewport_tag = '<meta name="viewport" content="width=device-width, initial-scale=1" />'
            content = content.replace('<head>', f'<head>\n    {viewport_tag}')
            changes.append("Added viewport meta tag")
        
        # Write changes if any were made
        if content != original_content:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            print(f"✅ Applied fixes: {changes}")
            return True
        else:
            print("✅ No fixes needed")
            return True
            
    except Exception as e:
        print(f"❌ Error fixing file: {str(e)}")
        return False

def fix_package_json(file_path):
    """Fix package.json for proper relative paths"""
    print(f"🔧 Fixing {file_path}...")
    
    if not os.path.exists(file_path):
        print(f"❌ File not found: {file_path}")
        return False
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        changes = []
        
        # Set homepage to relative
        if data.get('homepage') != '.':
            data['homepage'] = '.'
            changes.append("Set homepage to '.'")
        
        if changes:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
            
            print(f"✅ Applied fixes: {changes}")
        else:
            print("✅ No fixes needed")
            
        return True
        
    except Exception as e:
        print(f"❌ Error fixing package.json: {str(e)}")
        return False

def create_vite_config(directory):
    """Create proper Vite config for SPA routing"""
    vite_config_path = os.path.join(directory, "vite.config.js")
    
    if os.path.exists(vite_config_path):
        print(f"✅ Vite config already exists: {vite_config_path}")
        return True
    
    config_content = '''import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  base: "./",
  plugins: [react()],
  build: {
    outDir: 'dist',
    assetsDir: 'assets',
  }
})
'''
    
    try:
        with open(vite_config_path, 'w', encoding='utf-8') as f:
            f.write(config_content)
        
        print(f"✅ Created Vite config: {vite_config_path}")
        return True
        
    except Exception as e:
        print(f"❌ Error creating Vite config: {str(e)}")
        return False

def main():
    if len(sys.argv) != 2:
        print("Usage: python fix_blank_page.py <directory_path>")
        print("Example: python fix_blank_page.py ./build")
        print("         python fix_blank_page.py ./dist")
        sys.exit(1)
    
    directory = sys.argv[1]
    
    if not os.path.exists(directory):
        print(f"❌ Directory not found: {directory}")
        sys.exit(1)
    
    print("🚀 React Blank Page Quick Fix")
    print("=" * 40)
    
    # Find and fix index.html
    index_path = os.path.join(directory, "index.html")
    if os.path.exists(index_path):
        fix_index_html(index_path)
    else:
        print(f"❌ No index.html found in {directory}")
    
    # Check parent directory for package.json and fix it
    parent_dir = os.path.dirname(os.path.abspath(directory))
    package_json_path = os.path.join(parent_dir, "package.json")
    
    if os.path.exists(package_json_path):
        fix_package_json(package_json_path)
        
        # Check if it's a Vite project and create config if needed
        with open(package_json_path, 'r') as f:
            package_data = json.load(f)
            dependencies = package_data.get('dependencies', {})
            dev_dependencies = package_data.get('devDependencies', {})
            
            if 'vite' in dependencies or 'vite' in dev_dependencies:
                create_vite_config(parent_dir)
    
    print("\n" + "=" * 40)
    print("✅ Quick fix completed!")
    print("\n🔧 Manual steps you may still need:")
    print("1. Rebuild your React app")
    print("2. Re-upload to S3")
    print("3. Configure S3 bucket for static website hosting")
    print("4. Set S3 ErrorDocument to 'index.html'")

if __name__ == "__main__":
    main()  
