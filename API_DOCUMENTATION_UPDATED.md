# Updated API Documentation - Repository Management

## Overview

The repository management system has been updated to provide better React project detection and support for projects in subdirectories.

## Key Changes

1. **All repositories are now returned** without initial React detection
2. **Deep React project scanning** checks both root and subdirectories
3. **Project path detection** for React projects in subfolders
4. **Enhanced project structure analysis**

## API Endpoints

### 1. Get All Repositories

```http
GET /project/repos
```

**Description**: Returns all user repositories without React filtering.

**Response**:

```json
{
  "repos": [
    {
      "name": "my-repo",
      "full_name": "user/my-repo",
      "owner": "user",
      "description": "My awesome project",
      "clone_url": "https://github.com/user/my-repo.git",
      "updated_at": "2025-01-01T00:00:00Z",
      "private": false,
      "language": "JavaScript"
    }
  ],
  "docker_available": true
}
```

### 2. Check React Project (Enhanced)

```http
GET /project/check-react/{owner}/{repo}
```

**Description**: Deeply scans a repository to detect React projects in root or subdirectories.

**Response**:

```json
{
  "is_react": true,
  "project_path": "frontend",
  "package_json_path": "https://api.github.com/repos/user/repo/contents/frontend/package.json",
  "details": {
    "project_type": "Create React App",
    "has_react": true,
    "has_react_scripts": true,
    "has_vite": false,
    "has_build_script": true,
    "has_start_script": true,
    "dependencies": ["react", "react-dom"],
    "dev_dependencies": ["react-scripts"]
  }
}
```

**Fields**:

- `is_react`: Boolean indicating if React project was found
- `project_path`: Relative path to React project (empty string for root)
- `package_json_path`: GitHub API URL to the package.json file
- `details`: Detailed analysis of the React project

### 3. Get Repository Structure

```http
GET /project/repo-structure/{owner}/{repo}
```

**Description**: Returns detailed repository structure with React project locations.

**Response**:

```json
{
  "owner": "user",
  "repo": "repo-name",
  "structure": {
    "files": [
      {
        "name": "README.md",
        "size": 1024,
        "path": "README.md"
      }
    ],
    "directories": [
      {
        "name": "frontend",
        "path": "frontend"
      }
    ],
    "has_package_json": true,
    "react_projects": [
      {
        "path": "frontend",
        "location": "Subdirectory: frontend",
        "details": {
          "project_type": "Create React App",
          "has_react": true,
          "has_build_script": true
        }
      }
    ]
  },
  "total_react_projects": 1
}
```

### 4. Build React Project (Updated)

```http
POST /project/build/{owner}/{repo}
```

**Description**: Builds a React project, automatically detecting the correct subdirectory.

**Changes**:

- Automatically detects project location (root or subdirectory)
- Handles projects in subfolders
- Provides better error messages for non-React projects

**Response**: Same as before, but with enhanced path detection.

## Frontend Integration Examples

### Basic Repository List with React Detection

```javascript
// Fetch all repositories
const repos = await fetch("/api/project/repos").then((r) => r.json());

// Check if a specific repo is React
const reactCheck = await fetch(
  `/api/project/check-react/${owner}/${repo}`
).then((r) => r.json());

if (reactCheck.is_react) {
  console.log(`React project found in: ${reactCheck.project_path || "root"}`);
  console.log(`Project type: ${reactCheck.details.project_type}`);
}
```

### Building a Project in a Subdirectory

```javascript
// The build endpoint automatically handles subdirectories
const buildResult = await fetch(`/api/project/build/${owner}/${repo}`, {
  method: "POST",
}).then((r) => r.json());

if (buildResult.success) {
  console.log(`Built successfully! S3 URL: ${buildResult.s3_url}`);
}
```

### Repository Structure Analysis

```javascript
const structure = await fetch(
  `/api/project/repo-structure/${owner}/${repo}`
).then((r) => r.json());

console.log(`Found ${structure.total_react_projects} React projects:`);
structure.structure.react_projects.forEach((project) => {
  console.log(`- ${project.location} (${project.details.project_type})`);
});
```

## Use Cases

### 1. Monorepo with Multiple Projects

```
my-monorepo/
├── backend/         # Node.js API
├── frontend/        # React app ← Detected here
├── mobile/          # React Native
└── docs/            # Documentation
```

### 2. Project with Frontend Subfolder

```
my-project/
├── server/          # Backend code
├── client/          # React app ← Detected here
└── README.md
```

### 3. Root Level React Project

```
react-app/
├── src/             # React source
├── public/          # Static assets
├── package.json     # ← Detected here
└── README.md
```

## Migration Guide

If you're upgrading from the previous version:

1. **Repository List**: Remove React filtering from the frontend since all repos are now returned
2. **React Detection**: Use the new `/check-react` endpoint before building
3. **Error Handling**: Handle the new project path information
4. **UI Updates**: Show project location (root vs subdirectory) to users

## Error Handling

### Non-React Project

```json
{
  "is_react": false,
  "project_path": null,
  "package_json_path": null,
  "details": "No React project found in root or subdirectories"
}
```

### Build Error for Subdirectory Project

```json
{
  "success": false,
  "error": "Project path not found: frontend"
}
```

This updated system provides much more flexibility for detecting and building React projects in various repository structures.
