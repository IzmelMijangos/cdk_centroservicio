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
)
from constructs import Construct

class CdkCentroservicioStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        
        # Asumiendo que el nombre del secreto es "GitHubTokenSecret"
        github_token_secret = SecretValue.secrets_manager("GitHubTokenSecret")
        
        # Crear una nueva VPC con subredes públicas y privadas
        vpc = ec2.Vpc(self, "CSVpc",
                      max_azs=2,
                      subnet_configuration=[
                          ec2.SubnetConfiguration(name="Public", subnet_type=ec2.SubnetType.PUBLIC),
                          ec2.SubnetConfiguration(name="Private", subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS )
                      ])

       # ECR Repositories
        ecr_repository = ecr.Repository(self, "CSEcrRepository")

        # ECS Cluster
        ecs_cluster = ecs.Cluster(self, "CSCluster")

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

        # CodeBuild Project
        code_build_project = codebuild.PipelineProject(self, "CSProject",
            project_name="CSProject",
            environment={
                "build_image": codebuild.LinuxBuildImage.STANDARD_5_0,
                "privileged": True,
            },
            environment_variables={
                "ECR_REPOSITORY_URI": codebuild.BuildEnvironmentVariable(value=ecr_repository.repository_uri)
            }
        )

        ## Pipeline
        #source_output = codepipeline.Artifact()
        #build_output = codepipeline.Artifact()

        #pipeline = codepipeline.Pipeline(self, "CSPipeline",
        #    pipeline_name="CSPipeline",
        #    stages=[
        #        codepipeline.StageProps(
        #            stage_name="CSSource",
        #            actions=[
        #                codepipeline_actions.GitHubSourceAction(
        #                    action_name="GitHub_Source",
        #                    owner="IzmelMijangos",
        #                    repo="https://github.com/IzmelMijangos/CentroServicio.git",
        #                    oauth_token=SecretValue.secrets_manager("github_token_secret"),
        #                    output=source_output
        #                )
        #            ]
        #        ),
        #        codepipeline.StageProps(
        #            stage_name="CSBuild",
        #            actions=[
        #                codepipeline_actions.CodeBuildAction(
        #                    action_name="Docker_Build",
        #                    project=code_build_project,
        #                    input=source_output,
        #                    outputs=[build_output]
        #                )
        #            ]
        #        ),
        #        
        #    ]
        #)
        # Salidas
        CfnOutput(self, "VpcId", value=vpc.vpc_id)
        CfnOutput(self, "DBAddress", value=db_instance.db_instance_endpoint_address)
        CfnOutput(self, "DBPort", value=str(db_instance.db_instance_endpoint_port))