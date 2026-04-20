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

from dotenv import load_dotenv
load_dotenv(override=True)

if "db_connection" not in st.session_state:         
    st.session_state.db_connection = None


# ==========================================================
# LOGGING CONFIGURATION
# ==========================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler("sla_vector.log"),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)


# ==========================================================
# OCI CONFIGURATION
# ==========================================================


oracledb.init_oracle_client(lib_dir=r"C:\MySoft\instantclient_21_12")
CONFIG_PATH = r"C:\Users\Sathishkumar\.oci\config"
CONFIG_PROFILE = "DEFAULT"
COMPARTMENT_ID = "ocid1.compartment.oc1<yourCompartment_OCID>"
NAMESPACE = "sehubjapaciaas"
BUCKET_NAME = "DM_bucket"
PREFIX = "aiop"


# =========================
# Load API
# ========================
openai_api_key = os.getenv('OPENAI_API_KEY')
geo_api_key = os.getenv('GEOAPIFY_API_KEY')

if geo_api_key:
    print(f"OpenAI API Key exists and begins {openai_api_key[:10]}")
    print(f"OpenAI API Key exists and begins {geo_api_key[:10]}")
else:
    print("OpenAI API Key not set - please head to the troubleshooting guide in the setup folder")


# ==========================================================
# INIT OCI CLIENTS
# ==========================================================
def init_clients():  #using
    config = oci.config.from_file(CONFIG_PATH, CONFIG_PROFILE)

    ai_client = oci.ai_document.AIServiceDocumentClientCompositeOperations(
        oci.ai_document.AIServiceDocumentClient(config=config)
    )

    object_storage_client = oci.object_storage.ObjectStorageClient(config=config)

    return ai_client, object_storage_client


def geoapify_geocode(address):  #using

    try:
        url = "https://api.geoapify.com/v1/geocode/search"
        params = {
            "text": address,
            "apiKey": geo_api_key,
            "format": "json"
        }
    
        response = requests.get(url, params=params)
        data = response.json()

        if "results" in data and len(data["results"]) > 0:
            lat = data["results"][0]["lat"]
            lon = data["results"][0]["lon"]
            return lat, lon, None
        else:
            return None, None, "Location not found."

    except Exception as e:
        return None, None, str(e)
    




def fn_show_spatial_section(record):    #using
    st.header("Spatial Visualization")
    st.subheader("Using Oracle Spatial Geometry")

    address_parts = []
    if record.get("BLOCK_HOUSE"):
        address_parts.append(str(record["BLOCK_HOUSE"]))
        
    if record.get("STREET_NAME"):
        address_parts.append(str(record["STREET_NAME"]))

    if record.get("UNIT_NO"):
        address_parts.append(str(record["UNIT_NO"]))

    if record.get("POSTAL_CODE"):
        address_parts.append(str(record["POSTAL_CODE"]))

    #print('addres part',address_parts)
    auto_address = ", ".join(address_parts)


    user_address = st.text_input("Modify or Enter Address:", value=auto_address,key=f"address_input_{record['ID']}")

    left, center, right = st.columns([1,6,2])

    
    with center:

        if st.button("Visualize Location", key=f"viz_btn_{record['ID']}"):
            with st.spinner("Finding Spatial Location..."):
                lat, lon, error = geoapify_geocode(user_address)

                if error:
                    st.error(error)
                else:
                    st.success(f"Location Detected: Lat: {lat}, Lon: {lon}")
                    st.map(pd.DataFrame([[lat, lon]], columns=["lat", "lon"]),width="stretch")
                
    with right:
        if st.button("Close Map"):
            st.session_state.selected_row_data = None
            st.rerun()


def show_spatial_pydeck_map(df, selected_record):   #using

    lat_col = None
    lon_col = None

    for col in df.columns:
        if "LAT" in col:
            lat_col = col
        if "LON" in col:
            lon_col = col

    if lat_col and lon_col:

        # Rename for pydeck
        df = df.rename(columns={lat_col: "lat",lon_col: "lon"})
        df["type"] = df.get("AMENITY_TYPE", "Amenity")

        # Assign colors by type
        def get_color(t):
            t = str(t).upper()
            if "SCHOOL" in t:
                return [0, 102, 255]      # Blue
            elif "HOSPITAL" in t:
                return [0, 200, 0]       # Green
            else:
                return [255, 165, 0]     # Orange

        df["color"] = df["type"].apply(get_color)

        property_lat = selected_record.get("LAT")
        property_lon = selected_record.get("LON")

        property_df = pd.DataFrame({
            "lat": [property_lat],
            "lon": [property_lon],
            "NAME": ["PROPERTY"],
            "color": [[255,0,0]]
        })

        amenity_layer = pdk.Layer(
            "ScatterplotLayer",
            data=df,
            get_position='[lon, lat]',
            get_fill_color="color",
            get_radius=40,
            pickable=True
        )

        property_layer = pdk.Layer(
            "ScatterplotLayer",
            data=property_df,
            get_position='[lon, lat]',
            get_fill_color="color",
            get_radius=60
            )

        text_layer = pdk.Layer(
            "TextLayer",
            data=df,
            get_position='[lon, lat]',
            get_text="AMENITY_NAME",
            get_size=14,
            get_color=[255,255,255],
            get_angle=0,
            get_alignment_baseline="'bottom'"
        )

        view_state = pdk.ViewState(
            latitude=property_lat,
            longitude=property_lon,
            zoom=14
        )

        deck = pdk.Deck(layers=[amenity_layer, property_layer, text_layer],initial_view_state=view_state,tooltip={"html": "<b>{AMENITY_NAME}</b><br/>{AMENITY_TYPE}<br/>Distance: {DIST_KM} km"})
        st.subheader("Spatial Map Visualization")
        st.pydeck_chart(deck)

    else:
        st.warning("LAT/LON columns not found for map visualization.")


def fn_show_spatial_analytics_section(selected_record): #using

    st.header("Spatial Analytics")
    st.subheader("Using Oracle Select AI + Oracle Spatial Operators")

    question = st.text_input(
        "Ask spatial question:",
        placeholder="Example: Show all amenities within 500 meters for property id N"
    )
    if st.button("Run Spatial Analysis") and question: 

        with st.spinner("Generating Spatial Analytical Query.."):

            if st.session_state.db_connection is None:
                st.session_state.db_connection = get_db_connection()

            connection = st.session_state.db_connection

            result, error = fn_select_ai_spatial_analytics(
                connection,
                selected_record["ID"],
                question
            )

            if error:
                st.error(error)
                return

            with st.expander("Generated Spatial SQL"):
                st.code(result["generated_sql"], language="sql")

            if result["rows"]:
                df = pd.DataFrame(result["rows"], columns=result["columns"])
                st.subheader("Spatial Result")
                st.dataframe(df, width="stretch")

                df.columns = [col.upper() for col in df.columns]
                df = df.rename(columns={"LATITUDE": "LAT","LONGITUDE": "LON"})
                
                if "LAT" in df.columns and "LON" in df.columns:

                    st.subheader("Spatial Map Result")

                    # Amenity points
                    amenity_df = df[["LAT", "LON"]].rename(columns={"LAT": "lat", "LON": "lon"})

                    # Property location
                    property_lat = selected_record.get("LAT")
                    property_lon = selected_record.get("LON")

                    property_df = pd.DataFrame(
                        [[property_lat, property_lon]],
                        columns=["lat", "lon"]
                    )

                    # Combine both
                    map_df = pd.concat([property_df, amenity_df], ignore_index=True)

                    st.map(map_df, width="stretch")

                
                    show_spatial_pydeck_map(df, selected_record)

                else:
                    st.warning("Spatial coordinates not returned from query.")


            else:
                st.info("No spatial records found.")

# ==========================================================
# SUBMIT PROCESSOR JOB (TABLE + TEXT)
# ==========================================================
def submit_job(ai_client, file_bytes): #using

    encoded_file = base64.b64encode(file_bytes).decode("utf-8")

    table_feature = oci.ai_document.models.DocumentTableExtractionFeature()
    text_extraction_feature = oci.ai_document.models.DocumentTextExtractionFeature()

    output_location = oci.ai_document.models.OutputLocation(
        namespace_name=NAMESPACE,
        bucket_name=BUCKET_NAME,
        prefix=PREFIX
    )

    job_details = oci.ai_document.models.CreateProcessorJobDetails(
        display_name=str(uuid.uuid4()),
        compartment_id=COMPARTMENT_ID,
        input_location=oci.ai_document.models.InlineDocumentContent(data=encoded_file),
        output_location=output_location,
        processor_config=oci.ai_document.models.GeneralProcessorConfig(features=[table_feature,text_extraction_feature])
    )

    logger.info("Submitting processor job...")

    response = ai_client.create_processor_job_and_wait_for_state(
        create_processor_job_details=job_details,
        wait_for_states=[
            oci.ai_document.models.ProcessorJob.LIFECYCLE_STATE_SUCCEEDED
        ]
    )

    logger.info("Processor job completed.")

    return response.data


# ==========================================================
# FETCH RESULT JSON
# ==========================================================
def fetch_result(object_storage_client, job_id): #using

    object_name = f"{PREFIX}/{job_id}/_/results/defaultObject.json"

    logger.info(f"Fetching: {object_name}")

    response = object_storage_client.get_object(
        namespace_name=NAMESPACE,
        bucket_name=BUCKET_NAME,
        object_name=object_name
    )

    return json.loads(response.data.content.decode())


def fn_extract_property_from_json_v2(result_json, file_name): #using

    records = []

    pages = result_json.get("pages") or []

    for page in pages:
        tables = page.get("tables") or []

        for table in tables:
            body_rows = table.get("bodyRows") or []

            for row in body_rows:
                cells = row.get("cells") or []

                # Initialize record with defaults
                record = {
                    "SNO": None,
                    "FILE_NAME": file_name,
                    "BLOCK_HOUSE": None,
                    "STREET_NAME": None,
                    "STOREY": 0,
                    "UNIT_NO": 0,
                    "POSTAL_CODE": 0,
                    "LAT": 0,
                    "LON": 0
                }

                for cell in cells:
                    col_index = cell.get("columnIndex")
                    cell_text = (cell.get("text") or "").strip()

                    if col_index == 0:
                        record["SNO"] = cell_text

                    elif col_index == 1:
                        record["BLOCK_HOUSE"] = cell_text

                    elif col_index == 2:
                        record["STREET_NAME"] = cell_text

                    elif col_index == 3:
                        record["STOREY"] = int(cell_text) if cell_text.isdigit() else 0

                    elif col_index == 4:

                        clean_unit = cell_text.replace(" ", "")
                        record["UNIT_NO"] = int(clean_unit) if clean_unit.isdigit() else 0

                    elif col_index == 5:
                        record["POSTAL_CODE"] = int(cell_text) if cell_text.isdigit() else 0
                    elif col_index == 6:
                        try:
                            record["LAT"] = float(cell_text)
                        except:
                            record["LAT"] = 0

                    elif col_index == 7:
                        try:
                            record["LON"] = float(cell_text)
                        except:
                            record["LON"] = 0


                if str(record["SNO"]).strip().lower() == "s/no":
                    continue

                records.append(record)   
                #print(records)                 

    return records


def fn_records_to_dataframe(records):   #using
    if not records:
        return pd.DataFrame()

    df = pd.DataFrame(records)

    # enforce column order
    col_header = [
        "SNO", "BLOCK_HOUSE","STREET_NAME", "STOREY",
        "UNIT_NO", "POSTAL_CODE","LAT","LON","FILE_NAME"
    ]

    return df.reindex(columns=col_header)

# ==========================================================
# SAFE TEXT PARSER
# ==========================================================
def fn_parse_text_safe(result_json):    #using

    extracted_text = []

    try:
        pages = result_json.get("pages") or []

        for page in pages:
            lines = page.get("lines") or []

            for line in lines:
                text = line.get("text")
                if text:
                    extracted_text.append(text)

        #return "\n".join(extracted_text)
        logger.info(f"Total text lines extracted: {len(extracted_text)}")
        return "\n".join(extracted_text)

    except Exception as e:
        logger.error(f"Text parsing error: {str(e)}")
        raise

        
# ==========================================================
# # JSON VALIDATOR
# ==========================================================
def validate_document_json(result_json):    #using

    if not isinstance(result_json, dict):
        raise ValueError("Invalid OCI response: Not a dictionary")

    if "pages" not in result_json:
        raise ValueError("Invalid OCI response: 'pages' key missing")

    if not isinstance(result_json["pages"], list):
        raise ValueError("Invalid OCI response: 'pages' must be a list")

    return True


@st.cache_resource(show_spinner="Connnecting to Database...")
def get_db_connection():        #using
    print('connecting to db' + ' ' + str(datetime.now()))
    conn = oracledb.connect(
        user="appuser",
        password="MyPwd_123456",
        dsn="tns_ash26aifree_high"
        #,config_dir=WALLET_PATH
        )
    
    print('connected to db' + ' ' + str(datetime.now()))
    return conn


def fn_store_contact_data(connection, file_name, records):      #using

    cursor = connection.cursor()

    sql = """
        INSERT INTO SLA_PROPERTY_DETAILS_G
        (SNO,FILE_NAME, BLOCK_HOUSE, STREET_NAME, STOREY, UNIT_NO,POSTAL_CODE,LAT,LON)
        VALUES (:1, :2, :3, :4, :5,:6,:7,:8,:9)
    """
    #print(records)

    for rec in records:
        print("---")
        print(rec) 
        cursor.execute(sql, [
            rec.get("SNO"),
            file_name,
            rec.get("BLOCK_HOUSE"),
            rec.get("STREET_NAME"),
            rec.get("STOREY"),
            rec.get("UNIT_NO"),
            rec.get("POSTAL_CODE"),
            rec.get("LAT"),
            rec.get("LON")
        ])

    connection.commit()
    cursor.close()


# convert all LOB columns to string before creating the dataframe.
def convert_lob_rows(rows):                 #using
    clean_rows = []

    for row in rows:
        clean_row = []
        for value in row:
            if hasattr(value, "read"):      # LOB detected
                clean_row.append(value.read())
            else:
                clean_row.append(value)
        clean_rows.append(clean_row)

    return clean_rows

# ==========================================================
# 8/ SELECT AI NL2SQL CHATBOT ROUTINE
# 8/ SELECT AI NL2SQL CHATBOT ROUTINE (PROFILE SAFE)
# ==========================================================

def fn_run_select_ai_nl2sql_v3(connection, user_question): #using

    cursor = connection.cursor()

    try:
        cursor.execute("""
            BEGIN
                DBMS_CLOUD_AI.SET_PROFILE(
                    profile_name => 'SLA_PROP_DET_G'
                );
            END;
        """)

      # Wrap the user prompt with schema context
    
        system_prompt1 = f"""
                You are generating Oracle SQL for a table that contains prooerty details.

                IMPORTANT RULES:
                Use ONLY this table:
                SLA_PROPERTY_DETAILS_G

                Table Columns:
                        ID (NUMBER)
                        SNO varchar,
                        FILE_NAME  VARCHAR,
                        BLOCK_HOUSE VARCHAR,
                        STREET_NAME VARCHAR,
                        STOREY NUMBER,
                        UNIT_NO NUMBER,
                        POSTAL_CODE NUMBER
                        LAT NUMBER
                        LON NUMBER

                1. ALWAYS include the column ID in the SELECT list.
                2. ID must be the FIRST column in the SELECT statement.
                3.  Never omit ID under any condition.
                4. If the user mentions:
                - postal code → map to POSTAL_CODE column
                - pin code → map to POSTAL_CODE column
                - street → map to STREET_NAME column
                - unit → map to UNIT_NO column
                - house → map to BLOCK_HOUSE column
                - block → map to BLOCK_HOUSE column
                5. If a filter condition is mentioned, you MUST include a WHERE clause.
                -  If the user specifies any filter condition use that filter in where clause
                -  you MUST include a WHERE clause that strictly applies that condition.
                -  NEVER return all rows if a filter condition is mentioned.
                - Apply exact match filtering unless otherwise specified.
                6. Never ignore filtering instructions.
                -  Do not use SELECT *.
                - Generate valid Oracle SQL only.
                - Use exact column names.
                - Do not include explanations.
            
            very important:
            - ALWAYS include the column ID in the SELECT list along with User Question:
                User Question:
                {user_question}
                """
        
        
        cursor.execute("""
            SELECT DBMS_CLOUD_AI.GENERATE(
                prompt  => :1,
                action  => 'showsql'
            )
            FROM dual
        """, [system_prompt1])
        result = cursor.fetchone()

        if not result:
            return None, "No response returned."

        # Convert CLOB → string
        lob_data = result[0]
        generated_sql = lob_data.read() if hasattr(lob_data, "read") else str(lob_data)
        generated_sql = generated_sql.strip()

        cursor.execute(generated_sql)
        rows = cursor.fetchall()

        columns = [col[0].upper() for col in cursor.description]   # colname always return in uppercase
        
        # if any col in table is clob then this convert_lob_rows is  mandatory
        rows = convert_lob_rows(rows)       

        return {
            "generated_sql": generated_sql,
            "columns": columns,
            "rows": rows
            }, None

    except Exception as e:
        return None, str(e)

    finally:
        cursor.close()


def fn_select_ai_spatial_analytics(connection, property_id, user_question): #using

    cursor = connection.cursor()

    try:
        cursor.execute("""
            BEGIN
                DBMS_CLOUD_AI.SET_PROFILE(profile_name => 'SLA_SPAT_ANALY_MLLAMA4');
            END;
        """)
        
        cursor.execute("""SELECT DBMS_CLOUD_AI.GET_PROFILE() AS CURRENT_PROFILE FROM dual;""")
        result_curprofile = cursor.fetchone()
        
        print(result_curprofile)


        system_prompt_spatial = f"""
                                You are generating Oracle Spatial SQL.

                                IMPORTANT RULES:

                                Use ONLY these tables:

                                1. SLA_PROPERTY_DETAILS_G
                                Columns:
                                        ID NUMBER
                                        LAT NUMBER
                                        LON NUMBER
                                        LOC SDO_GEOMETRY

                                2. SINGAPORE_AMENTIES
                                Columns:
                                        AMENITY_NAME VARCHAR2
                                        AMENITY_TYPE VARCHAR2
                                        LOC SDO_GEOMETRY

                                Spatial Rules:

                                1. Property ID is {property_id}

                                2. ALWAYS include:
                                        a.AMENITY_NAME,
                                        a.LOC.SDO_POINT.Y AS LAT,
                                        a.LOC.SDO_POINT.X AS LON

                                3. Use spatial operators:

                                - SDO_WITHIN_DISTANCE for distance or radius search
                                - SDO_NN for nearest neighbour search
                                - sdo_geom.sdo_distance to calculate distance and show as DIST_KM
                                4. Join tables using:

                                FROM SINGAPORE_AMENTIES a,
                                    SLA_PROPERTY_DETAILS_G p

                                5. ALWAYS include:

                                p.ID = {property_id}

       
                                8. NEVER use SELECT *

                                9. Return valid Oracle SQL only

                                10. Do NOT explain anything.

                                User Question:
                                {user_question}
                                """

        cursor.execute("""
            SELECT DBMS_CLOUD_AI.GENERATE(
                prompt  => :1,
                action  => 'showsql'
            )
            FROM dual
        """, [system_prompt_spatial])

        result = cursor.fetchone()

        if not result:
            return None, "No response returned."

        lob_data = result[0]
        generated_sql = lob_data.read() if hasattr(lob_data, "read") else str(lob_data)
        generated_sql = generated_sql.strip()
        print(' SPAT generated_sql',generated_sql)
        cursor.execute(generated_sql)
        rows = cursor.fetchall()
        columns = [col[0].upper() for col in cursor.description]

        return {
            "generated_sql": generated_sql,
            "columns": columns,
            "rows": rows
        }, None

    except Exception as e:
        return None, str(e)

    finally:
        #result_curprofile.close()
        cursor.close()

          
# ==========================================================
# 9/ STREAMLIT SELECT AI CHATBOT UI
# ==========================================================

def select_ai_chatbot_ui_v1():  #using

    st.header("Chatbot - OCI Select AI ")

    if "open_dialog" not in st.session_state:
        st.session_state.open_dialog = False

    if "selected_row_data" not in st.session_state:
        st.session_state.selected_row_data = None
        print('st.session_state.selected_row_data-1',st.session_state.selected_row_data)

    if "show_map_popup" not in st.session_state:
        st.session_state.show_map_popup = False

    if "query_result" not in st.session_state:
        st.session_state.query_result = None


    user_question = st.text_input(
        "Ask a question about extracted contact data:",
        placeholder="Example: Show all customers from Chennai"
    )


    if st.button("Ask Select AI",key="ask_select_ai_button") and user_question:

        print('st.session_state-1',st.session_state.db_connection)
        if st.session_state.db_connection is None:
            print('st.session_state-2',st.session_state.db_connection)
            st.session_state.db_connection = get_db_connection()
            dbconnection = st.session_state.db_connection
            st.success("Database connected.")
            print('DB Connected')
        else:
            #st.info("Already connected.")
            print('st.session_state-3',st.session_state.db_connection)
            dbconnection = st.session_state.db_connection
            print('Already DB Connected')


        with st.spinner("Generating SQL using Oracle Select AI..."):

            result, error = fn_run_select_ai_nl2sql_v3(dbconnection,user_question)


            if error:
                st.error(error)
                return
            
            st.session_state.query_result = result


            with st.expander("Generated SQL"):
               st.code(result["generated_sql"], language="sql")                    


    if "query_result" in st.session_state and st.session_state.query_result != None :
        result = st.session_state.query_result
        if result and result["rows"]:

            df = pd.DataFrame(result["rows"],columns=result["columns"])


            st.subheader("Query Result")
                    
            if "ID" not in df.columns:
                st.error("ID column is required for spatial visualization.")
                st.dataframe(df)
                return
 
            col1, col2 = st.columns([4,1])  # 4:1 ratio
            with col1:   
                #st.subheader("Query Result")
                # Show dataframe normally
                st.dataframe(df, width='stretch')
       
            with col2:
                # Single selection using radio
                selected_id = st.radio("Select rec to vis:",options=df["ID"].tolist(),key="selected_id_radio")
                # Get selected record
                selected_record = df[df["ID"] == selected_id].iloc[0].to_dict()
                
            #selected_record = df[df["ID"] == selected_id].iloc[0].to_dict()
            st.session_state.selected_row_data = selected_record

        else:
            st.info("No rows returned.")
            #st.session_state.address_input(value="")


    print('st.session_state.selected_row_data-3',st.session_state.selected_row_data)
    if st.session_state.get("selected_row_data"):
        print('st.session_state.selected_row_data-4',st.session_state.selected_row_data)
        fn_show_spatial_section(st.session_state.selected_row_data)
        fn_show_spatial_analytics_section(st.session_state.selected_row_data)




# ==========================================================
# STREAMLIT UI (UPDATED - supports PDF + PNG + JPG)
# STREAMLIT UI
# include validation 
# ==========================================================
def streamlit_ui_v3():
    col1, col2, col3 = st.columns([6, 1, 2])
    shutdown_clicked = False
    with col3:
        if st.button("Exit"):
            shutdown_clicked = True

    if shutdown_clicked:            
        if "db_connection" in st.session_state:
            print('st.session_state-1',st.session_state.db_connection)
            if st.session_state.db_connection:
                try:
                    st.session_state.db_connection.close()
                    st.session_state.db_connection = None
                    print('DB Connection Closed')
                except:
                    print('st.session_state-except',st.session_state.db_connection)
                    pass

        
        print('st.session_state-3',st.session_state.db_connection)
        print('Shutting down application...')
        st.text("Shutting down application...")
        time.sleep(1)
        os._exit(0)



    st.title("OCI - Doc Understanding Service")
    st.header("Table & Text Extraction")

    uploaded_file = st.file_uploader(
        "Upload PDF or Image",
        type=["pdf", "png", "jpg", "jpeg"]
    )

    if uploaded_file and st.button("Extract & Store"):

        try:
            ai_client, object_storage_client = init_clients()

            file_bytes = uploaded_file.read()

            with st.spinner("Submitting document to OCI Document Understanding..."):
                processor_job = submit_job(ai_client, file_bytes)

            result_json = fetch_result(object_storage_client,processor_job.id)

            validate_document_json(result_json)
            records = fn_extract_property_from_json_v2(result_json,uploaded_file.name)

            extracted_text = fn_parse_text_safe(result_json)

            with st.expander("OCI Parsed Table and Text Output", expanded=True):

                col1, col2 = st.columns(2)

                # LEFT: Raw OCI Table
                with col1:
                    st.markdown("### Table Output")

                    parsed_df = fn_records_to_dataframe(records)
                    if not parsed_df.empty:
                        st.dataframe(parsed_df, width="stretch",height=500)  # if not to stretch width="content"
                    else:
                        st.info("No tables detected.")


                with col2:
                    st.markdown("### Parsed Text")
                    if extracted_text.strip():
                        st.text_area("Document Text",extracted_text,width="stretch",height=500)                    

                    else:
                        st.info("No text detected.")


            st.success("Extraction completed successfully.")

            fn_push2db(uploaded_file.name,records)
            st.success("Extraction and Storage Completed Successfully.")

        except Exception as e:
            st.error(str(e))

def fn_push2db(filename,records):   #using
    st.info("Connecting to Database to Insert")

    if st.session_state.db_connection is None:
        st.session_state.db_connection = get_db_connection()
        dbconnection = st.session_state.db_connection
        print('DB Connected')
    else:
        print('Already DB Connected')
    
    if records:
        fn_store_contact_data(st.session_state.db_connection,filename,records)

    st.info("Records Inserted")
# ==========================================================
# MAIN
# ==========================================================
if __name__ == "__main__":
    streamlit_ui_v3()
    st.divider()
    select_ai_chatbot_ui_v1()