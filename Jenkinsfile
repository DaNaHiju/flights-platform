pipeline {
    agent any

    environment {
        REGISTRY      = "myrepo"
        IMAGE_NAME    = "myapp"
        IMAGE_TAG     = "${env.BUILD_NUMBER}"
        FULL_IMAGE    = "${REGISTRY}/${IMAGE_NAME}:${IMAGE_TAG}"
        REGISTRY_CRED = credentials('docker-registry-credentials')
    }

    options {
        buildDiscarder(logRotator(numToKeepStr: '10'))
        timeout(time: 30, unit: 'MINUTES')
        timestamps()
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
                sh 'git log --oneline -5'
            }
        }

        stage('Lint') {
            steps {
                sh '''
                    pip install --quiet black pylint
                    echo "==> Running black (format check)"
                    black --check --diff app/
                    echo "==> Running pylint"
                    pylint app/ --fail-under=7.0
                '''
            }
        }

        stage('Unit Tests') {
            steps {
                sh '''
                    pip install --quiet -r requirements.txt
                    pytest tests/ \
                        --cov=app \
                        --cov-report=xml:coverage.xml \
                        --cov-report=term-missing \
                        -v
                '''
            }
            post {
                always {
                    junit allowEmptyResults: true, testResults: 'test-results/*.xml'
                    archiveArtifacts artifacts: 'coverage.xml', allowEmptyArchive: true
                }
            }
        }

        stage('Build Docker Image') {
            steps {
                sh """
                    docker build \
                        --tag ${IMAGE_NAME}:${IMAGE_TAG} \
                        --label "git-commit=${env.GIT_COMMIT}" \
                        --label "build-number=${IMAGE_TAG}" \
                        .
                """
            }
        }

        stage('Push to Registry') {
            steps {
                sh """
                    echo "${REGISTRY_CRED_PSW}" | docker login -u "${REGISTRY_CRED_USR}" --password-stdin

                    docker tag ${IMAGE_NAME}:${IMAGE_TAG} ${FULL_IMAGE}
                    docker push ${FULL_IMAGE}

                    # Also push a 'latest' tag on the main branch
                    if [ "${env.BRANCH_NAME}" = "main" ]; then
                        docker tag ${IMAGE_NAME}:${IMAGE_TAG} ${REGISTRY}/${IMAGE_NAME}:latest
                        docker push ${REGISTRY}/${IMAGE_NAME}:latest
                    fi

                    echo "${IMAGE_TAG}" > image_tag.txt
                """
                archiveArtifacts artifacts: 'image_tag.txt'
            }
        }

        stage('Update Manifests') {
            // Activate this stage once jenkins-argocd-manifests (Repo 2) is ready.
            when {
                expression { return false }
            }
            steps {
                /*
                withCredentials([usernamePassword(
                    credentialsId: 'github-credentials',
                    usernameVariable: 'GIT_USER',
                    passwordVariable: 'GIT_TOKEN'
                )]) {
                    sh """
                        git clone https://${GIT_USER}:${GIT_TOKEN}@github.com/user/jenkins-argocd-manifests.git
                        cd jenkins-argocd-manifests/helm/myapp

                        # Update image tag in values file
                        sed -i "s|tag:.*|tag: ${IMAGE_TAG}|" values.yaml

                        git config user.email "jenkins@ci.local"
                        git config user.name  "Jenkins CI"
                        git commit -am "chore: bump ${IMAGE_NAME} to ${IMAGE_TAG} [ci skip]"
                        git push
                    """
                }
                */
                echo 'Manifests stage is commented out — enable after Repo 2 is created.'
            }
        }
    }

    post {
        always {
            sh 'docker rmi ${IMAGE_NAME}:${IMAGE_TAG} || true'
            cleanWs()
        }
        success {
            echo "Build ${IMAGE_TAG} succeeded. Image: ${FULL_IMAGE}"
        }
        failure {
            echo "Build ${IMAGE_TAG} failed. Check the logs above."
        }
    }
}
