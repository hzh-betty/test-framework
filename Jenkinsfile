pipeline {
  agent any

  parameters {
    booleanParam(name: 'WEBTEST_DEPLOY', defaultValue: false, description: 'Run deployment commands before tests')
  }

  environment {
    SMTP_PASSWORD = credentials('smtp-password')
    DINGTALK_WEBHOOK = credentials('dingtalk-webhook')
    WECOM_WEBHOOK = credentials('wecom-webhook')
    FEISHU_WEBHOOK = credentials('feishu-webhook')
  }

  stages {
    stage('Checkout') {
      steps {
        checkout scm
      }
    }
    stage('Install') {
      steps {
        sh 'uv sync --dev'
      }
    }
    stage('Dry Run') {
      steps {
        sh '''
          DEPLOY_FLAG=""
          if [ "${WEBTEST_DEPLOY}" = "true" ]; then
            DEPLOY_FLAG="--deploy"
          fi
          uv run webtest-framework examples/cases/web_actions_extended.yaml --config examples/config/runtime.yaml --dry-run --stats-output artifacts/statistics.json ${DEPLOY_FLAG}
        '''
      }
    }
    stage('Test') {
      steps {
        sh 'uv run webtest-framework examples/cases/web_actions_extended.yaml --config examples/config/runtime.yaml --notify --stats-output artifacts/statistics.json'
      }
    }
  }

  post {
    always {
      archiveArtifacts artifacts: 'artifacts/**', allowEmptyArchive: true
    }
  }
}
