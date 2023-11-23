from aws_cdk import (
    Stack, 
    Duration,
    aws_rds as rds,
    aws_secretsmanager as secretsmanager,
    aws_elasticloadbalancingv2 as elbv2,
    aws_ecs as ecs,
    aws_ecr as ecr,
    aws_codebuild as codebuild,
    aws_codepipeline as codepipeline,
    aws_codepipeline_actions as codepipeline_actions,
    aws_ec2 as ec2,
    aws_secretsmanager as sm,
    CfnOutput,
    SecretValue,
    Duration,
    aws_iam as iam,
    aws_codestarconnections as codestarconnections
)
from constructs import Construct

class CdkCentroservicioStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        
        # Crear una nueva VPC con subredes públicas y privadas
        vpc = ec2.Vpc(self, "CSVpc",
                      max_azs=2,
                      subnet_configuration=[
                          ec2.SubnetConfiguration(name="Public", subnet_type=ec2.SubnetType.PUBLIC),
                          ec2.SubnetConfiguration(name="Private", subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS )
                      ])

        # Define un recurso de AWS CodeStar Connections y obtiene el ARN
        codestar_connection = codestarconnections.CfnConnection(
            self, "MyCodeStarConnection",
            connection_name="MyConnection",
            provider_type="GitHub",
        )
        connection_arn = codestar_connection.attr_connection_arn

        # Crea el repositorio en ECR
        ecr_repository = ecr.Repository(self, "CSEcrRepository")

        # Fuente del artefacto para el código fuente
        source_output = codepipeline.Artifact()
        # Definir un artefacto de salida para la imagen construida
        build_output = codepipeline.Artifact()
        
        # Crear un rol de IAM para CodeBuild con permisos para interactuar con ECR
        codebuild_role = iam.Role(self, "CodeBuildRole",
            assumed_by=iam.ServicePrincipal("codebuild.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("AmazonEC2ContainerRegistryPowerUser"),
            ]
        )
        
        # Crear un proyecto de CodeBuild para construir y subir la imagen Docker
        build_project = codebuild.PipelineProject(self, "BuildProject",
            build_spec=codebuild.BuildSpec.from_object({
                'version': '0.2',
                'phases': {
                    'pre_build': {
                        'commands': [
                            'echo Logging in to Amazon ECR...',
                            '$(aws ecr get-login --region $AWS_DEFAULT_REGION --no-include-email)',
                        ]
                    },
                    'build': {
                        'commands': [
                            'echo Build started on `date`',
                            'echo Building the Docker image...',
                            'docker build -t $REPOSITORY_URI:backend -f Dockerfile.back.prod .',
                        ]
                    },
                    'post_build': {
                        'commands': [
                            'echo Build completed on `date`',
                            'echo Pushing the Docker image...',
                            'docker push $REPOSITORY_URI:backend',
                            'echo Writing image definitions file...',
                            'printf \'[{"name":"CSEcrRepository","imageUri":"%s"}]\' $REPOSITORY_URI:backend > imagedefinitions.json',
                        ]
                    }
                },
                'artifacts': {
                    'files': ['imagedefinitions.json']
                },
                'environment': {
                    'privileged-mode': True,
                    'buildImage': codebuild.LinuxBuildImage.STANDARD_5_0,
                },
            }),
            environment_variables={
                'REPOSITORY_URI': codebuild.BuildEnvironmentVariable(value=ecr_repository.repository_uri)
            },
            role=codebuild_role,
        )
        # Asegúrate de que el proyecto CodeBuild tenga permisos para interactuar con ECR
        ecr_repository.grant_pull_push(build_project)

        # Pipeline de CodePipeline
        pipeline = codepipeline.Pipeline(self, "CSPipeline",
            stages=[
                codepipeline.StageProps(
                    stage_name='Source',
                    actions=[
                        codepipeline_actions.CodeStarConnectionsSourceAction(
                            action_name="GitHub_Source",
                            owner="IzmelMijangos",
                            repo="CentroServicioBackend",
                            branch="master",
                            connection_arn=connection_arn,
                            output=source_output,
                            ),
                        ]
                ),
                codepipeline.StageProps(
                    stage_name='Build',
                    actions=[
                        codepipeline_actions.CodeBuildAction(
                            action_name='Build',
                            project=build_project,
                            input=source_output,
                            outputs=[build_output],
                        ),
                    ]
                ),
                codepipeline.StageProps(
                    stage_name='Mock',
                    actions=[
                        codepipeline_actions.ManualApprovalAction(
                            action_name='Manual_Approval',
                            run_order=1
                        )
                    ]
                ),
            ],
        )

        # Crear un secreto para la contraseña de la base de datos
        db_password = sm.Secret(self, "CSDBPassword",
            generate_secret_string=sm.SecretStringGenerator(
                secret_string_template='{"username": "dbadmin"}',
                exclude_characters='{}[]()\'"/\\ @',  # Añadido '@' y espacio a la lista de excluidos
                generate_string_key='password'
            )
        )

        # Instancia de Base de Datos
        db_instance = rds.DatabaseInstance(
            self, "CSDatabase",
            engine=rds.DatabaseInstanceEngine.postgres(
                version=rds.PostgresEngineVersion.VER_12
            ),
            instance_type=ec2.InstanceType.of(
                ec2.InstanceClass.BURSTABLE2, ec2.InstanceSize.MICRO
            ),
            vpc=vpc,
            vpc_subnets={
                "subnet_type": ec2.SubnetType.PRIVATE_WITH_EGRESS
            },
            credentials=rds.Credentials.from_secret(db_password),
            multi_az=False,
            allocated_storage=20,
            max_allocated_storage=100,
            allow_major_version_upgrade=False,
            auto_minor_version_upgrade=True,
            delete_automated_backups=True,
            deletion_protection=False,
            publicly_accessible=False,
            storage_encrypted=False,
            storage_type=rds.StorageType.GP2,
            backup_retention=Duration.days(7),
            enable_performance_insights=True,
            performance_insight_retention=rds.PerformanceInsightRetention.DEFAULT,
            parameter_group=rds.ParameterGroup.from_parameter_group_name(
                self, "ParameterGroup",
                parameter_group_name="default.postgres12"
            ),
        )