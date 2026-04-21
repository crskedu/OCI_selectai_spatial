# OCI_selectai_spatial
Application built to demonstrate Oracle Document Understanding + Select AI + Spatial using Python, Streamlit

Prerequisite:

P1:    Install and Configure OCI Command Line Interface (CLI)
  Ref: https://docs.oracle.com/en-us/iaas/Content/API/SDKDocs/cliinstall.htm#configfile
  
  Ref: https://docs.oracle.com/en/cloud/paas/autonomous-database/serverless/adbsb/dbms-cloud-subprograms.html#GUID-742FC365-AA09-48A8-922C-1987795CF36A

P2: Create Profiles
  Ref: https://docs.oracle.com/en-us/iaas/autonomous-database-serverless/doc/dbms-cloud-ai-package.html  

P3: Python Modules required

import os
import streamlit as st
import oci
import base64
import uuid
import json
import logging
import pandas as pd
from datetime import datetime
import oracledb
import re
import oci.generative_ai_inference as genai
from openai import OpenAI
import sys
import time
import requests
import pydeck as pdk


Short Video of this application, can be viewed here =>  https://youtu.be/3Pnn0OiOGjQ
