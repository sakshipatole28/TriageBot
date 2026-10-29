// Jenkins CI/CD pipeline, same idea as GitHub Actions:
// Checkout -> Test -> Docker Build -> Run container + curl /health -> Deploy to Kubernetes (kind).
// The Jenkins machine needs: python3 (with venv), docker, curl, kind, kubectl,
// the jenkins user in the docker group, and a "Secret text" credential with ID groq-api-key.
// The app stays deployed after the build at http://localhost:30080.
pipeline {
    agent any

    // GitHub webhooks cannot reach a laptop, so check the repo for new commits every ~5 minutes.
    triggers {
        pollSCM('H/5 * * * *')
    }

    environment {
        IMAGE     = "triagebot:${BUILD_NUMBER}"
        CONTAINER = "triagebot-jenkins-${BUILD_NUMBER}"
        HOST_PORT = "8001"          // avoid clashing with anything already on 8000
        PIP_DEFAULT_TIMEOUT = "300" // survive a slow network while installing packages
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
            }
        }

        stage('Test') {
            steps {
                sh '''
                    python3 -m venv .venv
                    . .venv/bin/activate
                    pip install -r requirements.txt
                    pytest -v --junitxml=test-results.xml
                '''
            }
        }

        stage('Docker Build') {
            steps {
                // host network: pip inside the build uses the host's connection (avoids timeouts)
                sh 'docker build --network=host -t "$IMAGE" .'
            }
        }

        stage('Run & Health Check') {
            steps {
                sh '''
                    docker run -d --name "$CONTAINER" -p "$HOST_PORT:8000" "$IMAGE"
                    for i in $(seq 1 30); do
                        if curl -fsS "http://localhost:$HOST_PORT/health"; then
                            echo; echo "Health check passed"; exit 0
                        fi
                        sleep 2
                    done
                    echo "Health check failed"; docker logs "$CONTAINER"; exit 1
                '''
            }
        }

        stage('Deploy to Kubernetes') {
            steps {
                // The key is masked in the console log and only exists during this step.
                withCredentials([string(credentialsId: 'groq-api-key', variable: 'GROQ_API_KEY')]) {
                    sh './scripts/deploy-k8s.sh "$IMAGE"'
                }
            }
        }
    }

    post {
        always {
            junit allowEmptyResults: true, testResults: 'test-results.xml'
            sh 'docker rm -f "$CONTAINER" || true'
        }
    }
}
