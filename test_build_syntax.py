#!/usr/bin/env python3
"""
Quick Test for Build Command Syntax
Tests the shell command syntax that's used in the Docker build
"""

import subprocess
import tempfile
import os

def test_shell_command():
    """Test if our shell command syntax works"""
    
    # Create a simple test command similar to our build
    test_command = [
        "sh", "-c", 
        """
        set -e
        echo "🚀 Testing shell command syntax..."
        echo "📦 Running test build..."
        
        # Test the build command structure we're using
        echo "fake build output" > /tmp/test_output.log 2>&1
        BUILD_EXIT_CODE=$?
        
        if [ $BUILD_EXIT_CODE -ne 0 ]; then
            echo "❌ Build failed!"
            echo "Exit code: $BUILD_EXIT_CODE"
            exit 1
        else
            echo "✅ Build syntax test passed!"
        fi
        
        echo "📊 Test completed successfully"
        """
    ]
    
    try:
        print("Testing shell command syntax...")
        result = subprocess.run(
            test_command,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        print(f"Exit code: {result.returncode}")
        print(f"STDOUT:\n{result.stdout}")
        
        if result.stderr:
            print(f"STDERR:\n{result.stderr}")
        
        if result.returncode == 0:
            print("✅ Shell command syntax is working correctly!")
            return True
        else:
            print("❌ Shell command failed")
            return False
            
    except subprocess.TimeoutExpired:
        print("❌ Command timed out")
        return False
    except Exception as e:
        print(f"❌ Error running test: {str(e)}")
        return False

def test_node_command():
    """Test if Node.js commands work in Alpine container"""
    
    docker_test_command = [
        "docker", "run", "--rm", 
        "node:20-alpine",
        "sh", "-c",
        """
        echo "Node version: $(node --version)"
        echo "NPM version: $(npm --version)"
        echo "✅ Node.js 20 is working!"
        """
    ]
    
    try:
        print("\nTesting Node.js in Docker...")
        result = subprocess.run(
            docker_test_command,
            capture_output=True,
            text=True,
            timeout=60
        )
        
        print(f"Exit code: {result.returncode}")
        print(f"Output:\n{result.stdout}")
        
        if result.stderr:
            print(f"Errors:\n{result.stderr}")
        
        if result.returncode == 0:
            print("✅ Node.js Docker test passed!")
            return True
        else:
            print("❌ Node.js Docker test failed")
            return False
            
    except subprocess.TimeoutExpired:
        print("❌ Docker command timed out")
        return False
    except Exception as e:
        print(f"❌ Error running Docker test: {str(e)}")
        return False

def main():
    print("🧪 Build Command Testing")
    print("=" * 40)
    
    # Test 1: Shell command syntax
    shell_test = test_shell_command()
    
    # Test 2: Docker Node.js
    docker_test = test_node_command()
    
    print("\n" + "=" * 40)
    print("📊 Test Results:")
    print(f"Shell Command Syntax: {'✅ PASS' if shell_test else '❌ FAIL'}")
    print(f"Docker Node.js Test:  {'✅ PASS' if docker_test else '❌ FAIL'}")
    
    if shell_test and docker_test:
        print("\n🎉 All tests passed! Build should work now.")
    else:
        print("\n⚠️  Some tests failed. Check the errors above.")

if __name__ == "__main__":
    main()
