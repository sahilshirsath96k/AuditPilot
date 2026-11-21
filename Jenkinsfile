
pipeline {
    agent any

    environment {
        AWS_REGION     = 'ap-south-1'
        AWS_ACCOUNT_ID = '469465348676'
        ECR_REPOSITORY = 'auditpilot'
        IMAGE_NAME     = 'auditpilot'
        AWS_CREDENTIALS = 'aws-credentials'
    }

    stages {

        stage('Checkout GitHub') {
            steps {
                checkout scm
            }
        }

        stage('Install Dependencies') {
            steps {
                sh '''
                    python3 -m venv .venv-ci
                    .venv-ci/bin/pip install --upgrade pip
                    .venv-ci/bin/pip install -r requirements-dev.txt
                '''
            }
        }

        stage('Backend Tests') {
            steps {
                sh '''
                    .venv-ci/bin/pytest -q tests/
                '''
            }
        }

        stage('Build Docker Image') {
            steps {
                sh '''
                    docker build \
                      -t ${IMAGE_NAME}:${BUILD_NUMBER} \
                      -t ${IMAGE_NAME}:latest .
                '''
            }
        }

        stage('Push Image to Amazon ECR') {
            steps {
                withCredentials([
                    usernamePassword(
                        credentialsId: "${AWS_CREDENTIALS}",
                        usernameVariable: 'AWS_ACCESS_KEY_ID',
                        passwordVariable: 'AWS_SECRET_ACCESS_KEY'
                    )
                ]) {
                    sh '''
                        set -e

                        export AWS_DEFAULT_REGION="$AWS_REGION"

                        ECR_URI="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPOSITORY}"

                        aws ecr get-login-password --region "$AWS_REGION" |
                            docker login \
                            --username AWS \
                            --password-stdin \
                            "${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"

                        docker tag "${IMAGE_NAME}:${BUILD_NUMBER}" "${ECR_URI}:${BUILD_NUMBER}"
                        docker tag "${IMAGE_NAME}:latest" "${ECR_URI}:latest"

                        docker push "${ECR_URI}:${BUILD_NUMBER}"
                        docker push "${ECR_URI}:latest"
                    '''
                }
            }
        }
    }

    post {
        success {
            echo 'AuditPilot tests passed and Docker image pushed to ECR.'
        }

        failure {
            echo 'AuditPilot pipeline failed. Check the failed stage logs.'
        }

        always {
            echo 'AuditPilot CI/CD pipeline execution completed.'
        }
    }
}

