#!/usr/bin/env python3
import os

import aws_cdk as cdk

from cdk_centroservicio.cdk_centroservicio_stack import CdkCentroservicioStack


app = cdk.App()
CdkCentroservicioStack(app, "CdkCentroservicioStack",
    env=cdk.Environment(account=os.getenv('CDK_DEFAULT_ACCOUNT'), 
    region=os.getenv('CDK_DEFAULT_REGION'))
)

app.synth()