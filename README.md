# OCI_selectai_spatial
Application built to demonstrate Oracle Document Understanding + Select AI + Spatial using Python, Streamlit

Modules required

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
