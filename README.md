# Hoster_clg - Project Hosting Platform

A platform to build and host React projects from GitHub repositories.

## Features

- GitHub OAuth authentication
- React project building using Docker
- S3 integration for hosting built projects
- API endpoints for project management

## Setup

1. Install dependencies:

```bash
pip install -r requirment.txt
```

2. Configure environment variables:

   - Copy `sample.env` to `.env` and update the values
   - Required GitHub OAuth settings: `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET`, `CALLBACK_URL`
   - Required S3 settings: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `S3_BUCKET_NAME`

3. Run the application:

```bash
cd Hoster
uvicorn app.main:app --reload
```

## S3 Integration

### Configuration

To enable S3 hosting, set these environment variables in your `.env` file:

```
AWS_ACCESS_KEY_ID=your_aws_access_key_id
AWS_SECRET_ACCESS_KEY=your_aws_secret_access_key
AWS_REGION=us-east-1
S3_BUCKET_NAME=your-bucket-name
S3_BASE_URL=https://your-bucket-name.s3.amazonaws.com/
```

For custom domain hosting:

1. Set up your domain with your DNS provider to point to your S3 bucket
2. Configure `S3_BASE_URL` to use your custom domain:

```
S3_BASE_URL=https://your-custom-domain.com/
```

### CORS Configuration for S3 Bucket

If you're hosting the React application on S3, you'll need to configure CORS for your bucket:

1. Go to your S3 bucket in the AWS Management Console
2. Navigate to the "Permissions" tab
3. Scroll down to the "Cross-origin resource sharing (CORS)" section
4. Add the following CORS configuration:

```json
[
  {
    "AllowedHeaders": ["*"],
    "AllowedMethods": ["GET", "HEAD"],
    "AllowedOrigins": ["*"],
    "ExposeHeaders": []
  }
]
```

### API Endpoints

- `POST /project/build/{owner}/{repo}` - Build and deploy a React project
- `GET /project/builds` - List all built projects
- `GET /project/s3-info/{owner}/{repo}` - Get S3 hosting information for a project
- `DELETE /project/s3/{owner}/{repo}` - Delete a project from S3 storage
- `DELETE /project/builds/{build_id}` - Delete a locally built project

## Frontend Integration

To display S3 hosting information in your frontend, update your React components to handle the S3 URL information from the API responses.
