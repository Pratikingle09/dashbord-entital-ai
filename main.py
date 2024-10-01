import streamlit as st
import pandas as pd
import plotly.express as px
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
import os


# Set page configuration
st.set_page_config(layout="wide")
st.title("Welcome to Data Visualization Dashboard with OAuth")

def calculate_velocity(total_actual, total_estimate):
    return total_actual / total_estimate if total_estimate != 0 else 0



client_id=st.secrets["google"]["client_id"]
client_secret=st.secrets["google"]["client_secret"]
redirect_uris=st.secrets["google"]["redirect_uris"][0]

# OAuth credentials setup
CLIENT_SECRETS_FILE = {
  "web": {
    "client_id": client_id,
    "project_id": "data-visualization-436504",
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token",
    "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
    "client_secret": client_secret,
    "redirect_uris": redirect_uris
  }
}
                      #"credentials.json"  
SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly']

# Initialize session state for credentials
if 'credentials' not in st.session_state:
    st.session_state.credentials = None

# Set up the OAuth flow
def create_flow():
    flow = Flow.from_client_secrets_file(CLIENT_SECRETS_FILE, scopes=SCOPES, redirect_uri='http://localhost:8501/')
    return flow

# Check if user is logged in
def is_logged_in():
    if st.session_state.credentials is None:
        return False
    if not st.session_state.credentials.valid:
        if st.session_state.credentials.expired and st.session_state.credentials.refresh_token:
            st.session_state.credentials.refresh(Request())
        else:
            return False
    return True

# Login function
def login():
    flow = create_flow()
    auth_url, _ = flow.authorization_url(prompt='consent')
    st.write(f'Please [authorize]({auth_url}) to access your Google Sheets.')

# Logout function
def logout():
    if 'credentials' in st.session_state:
        del st.session_state['credentials']
    st.success("You have been logged out.")

# Process the OAuth callback
def process_oauth_code():
    flow = create_flow()
    code = st.experimental_get_query_params().get('code')
    if code:
        flow.fetch_token(code=code[0])
        credentials = flow.credentials
        st.session_state.credentials = credentials
        st.experimental_set_query_params()  # Clear the query parameters

# Google Sheets API helper function to get sheet names
def get_sheet_names(sheet_id, credentials):
    service = build('sheets', 'v4', credentials=credentials)
    spreadsheet = service.spreadsheets().get(spreadsheetId=sheet_id).execute()
    sheets = spreadsheet.get('sheets', [])
    sheet_names = [sheet['properties']['title'] for sheet in sheets]
    return sheet_names

# Function to fetch data from the selected sheet
def fetch_sheet_data(sheet_id, sheet_name, credentials):
    service = build('sheets', 'v4', credentials=credentials)
    sheet = service.spreadsheets()
    
    # Read the spreadsheet data for the selected sheet
    result = sheet.values().get(spreadsheetId=sheet_id, range=sheet_name).execute()
    values = result.get('values', [])
    
    if values:
        # Ensure all rows have the same number of columns as the header
        num_cols = len(values[0])  # Get the number of columns in the header
        for row in values:
            if len(row) < num_cols:
                row.extend([None] * (num_cols - len(row)))  # Fill missing columns with None

        # Convert the spreadsheet values into a pandas DataFrame
        df = pd.DataFrame(values[1:], columns=[col.lower() for col in values[0]])  # Lowercase the column headers
    else:
        df = pd.DataFrame()
    
    return df


# Main logic
process_oauth_code()

if is_logged_in():
    st.success("You are logged in.")
    if st.button("Logout"):
        logout()

    shared_url = st.text_input("Enter the Google Sheet URL:")

    if shared_url:
        try:
            # Extract Google Sheet ID from the URL
            sheet_id = shared_url.split('/')[5]
            
            # Fetch available sheets
            credentials = st.session_state.credentials
            sheet_names = get_sheet_names(sheet_id, credentials)

            # Display a select box to choose the sheet
            selected_sheet = st.selectbox("Select a sheet to visualize:", sheet_names)

            if st.button("Visualize"):
                if selected_sheet:
                    table = fetch_sheet_data(sheet_id, selected_sheet, credentials)
                    
                    if not table.empty:
                        # Convert columns to appropriate data types
                        table['actual'] = pd.to_numeric(table['actual'], errors='coerce')
                        table['estimate'] = pd.to_numeric(table['estimate'], errors='coerce')

                        # Dev Time Difference
                        table['dev time difference'] = table['actual'] - table['estimate']

                        st.subheader("Sprint Health")
                        col1, col2 = st.columns(2)

                        with col1:
                            total_estimate = table['estimate'].sum()
                            total_actual = table['actual'].sum()
                            velocity = calculate_velocity(total_actual, total_estimate)

                            time_difference = total_estimate - total_actual
                            hours = int(abs(time_difference))
                            minutes = int((abs(time_difference) - hours) * 60)

                            time_status = "**On Time**" if velocity == 0 else \
                                        f"**Behind Schedule** by {hours}h {minutes}m" if velocity > 0 else \
                                        f"**Ahead of Time** by {hours}h {minutes}m"

                            st.write(f"Velocity: {velocity:.2f}")
                            st.write(f"Sprint status: {time_status}")

                            velocity_fig = px.bar(
                                x=['ESTIMATE', 'ACTUAL'],
                                y=[total_estimate, total_actual],
                                labels={'x': 'Type of Effort', 'y': 'Effort (hours)'},
                                title='Team Sprint Velocity',
                                text=[total_estimate, total_actual],
                            )
                            velocity_fig.update_layout(bargap=0.7)
                            velocity_fig.update_traces(textposition='outside')
                            velocity_fig.update_layout(showlegend=False, xaxis_title='', yaxis_title='Effort (hours)')
                            st.plotly_chart(velocity_fig)

                        with col2:
                            table['risks'] = table['risks'].fillna('').str.lower()
                            risk_counts = table['risks'].value_counts().reset_index()
                            risk_counts.columns = ['Risk Type', 'Count']
                            risk_counts['Risk Type'] = risk_counts['Risk Type'].replace({
                                'no risks': 'No Risk',
                                '': 'No Risk',
                                'nil': 'No Risk',
                                'not yet identified': 'Not Yet Identified'
                            })

                            color_map = {
                                'Not Yet Identified': 'yellow',
                                'No Risk': 'green',
                                'risk': 'red' 
                            }

                            risk_counts['Risk Type'] = risk_counts['Risk Type'].where(
                                risk_counts['Risk Type'].isin(['No Risk', 'Not Yet Identified']),
                                'risk'
                            )

                            fig = px.pie(
                                risk_counts, 
                                names='Risk Type',  
                                values='Count', 
                                title='Risk Distribution',
                                color='Risk Type', 
                                color_discrete_map=color_map, 
                                hole=0.4, 
                                height=500
                            )
                            fig.update_traces(
                                hovertemplate="<b>%{label}</b><br>Count: %{value}<extra></extra>" 
                            )
                            st.plotly_chart(fig)

                        # Create a new DataFrame for plotting
                        plot_data = table[['task_name', 'estimate', 'actual']].copy()
                        plot_data['task_name'] = plot_data['task_name'].fillna('')  # Fill NaN with empty strings
                        plot_data['task-name'] = plot_data['task_name'].str.slice(0, 5) + '...'

                        # Replace NaN in 'actual' with 0 for plotting purposes
                        plot_data['actual'] = plot_data['actual'].fillna(0)
                        plot_data['estimate'] = plot_data['estimate'].fillna(0)

                        # Create a new column to represent task status
                        plot_data['Status'] = plot_data.apply(
                            lambda row: 'Yet to Start' if row['estimate'] == 0 and row['actual'] == 0
                            else 'In Progress' if row['actual'] == 0
                            else 'Completed', axis=1
                        )

                        # Add a custom value for 'Actual' where it's missing to differentiate
                        plot_data['Actual'] = plot_data.apply(
                            lambda row: 0.01 if row['Status'] == 'In Progress' else row['actual'], axis=1
                        )

                        # Create the grouped bar chart with task progress (Estimate and Actual side by side)
                        fig = px.bar(
                            plot_data,
                            x='task-name',
                            y=['estimate', 'Actual'],
                            barmode='group',
                            title="Estimate vs Actual Task Time",
                            labels={'value': 'Hours', 'variable': 'Type'},
                            text_auto=True,
                            height=600,
                            hover_data={'task-name': False, 'task_name': True}
                        )

                        # Update the bar colors and labels
                        fig.update_traces(marker=dict(color=['yellow', '#ff7f0e']), selector=dict(name='actual'))
                        fig.for_each_trace(lambda trace: trace.update(textposition='outside'))

                        # Show in-progress and yet to start as specific colors or labels
                        for i in range(len(plot_data)):
                            if plot_data['Status'].iloc[i] == 'In Progress':
                                fig.add_annotation(
                                    x=plot_data['task-name'].iloc[i],
                                    y=0.15, 
                                    text="In Progress",
                                    showarrow=False,
                                    font=dict(color="yellow"),
                                    align="center",
                                    textangle=-90,  
                                    yshift=50,
                                    xshift=20,
                                )
                            elif plot_data['Status'].iloc[i] == 'Yet to Start':
                                fig.add_annotation(
                                    x=plot_data['task-name'].iloc[i],
                                    y=0.15,  # Position the text slightly above the zero line
                                    text="Yet to Start",
                                    showarrow=False,
                                    font=dict(color="orange"),
                                    align="center",
                                    textangle=-90, 
                                    yshift=30,
                                )

                        st.plotly_chart(fig)

                        # Task/Module Time Visualization
                        col3, col4 = st.columns(2)

                        with col3:
                            st.subheader("Task Time/Module Time")
                            table['task-name'] = table['task_name'].str.slice(0, 5) + '...'

                            task_time_fig = px.bar(table, x='task-name', y='estimate', title="Time per Task",
                                                    hover_data={'task-name': False, 'task_name': True})
                            st.plotly_chart(task_time_fig)

                        with col4:
                            st.subheader("Dev Time (Actual)")

                            dev_time_fig = px.bar(
                                table,
                                x='task-name',
                                y='actual',
                                title="Dev Time",
                                hover_data={'task-name': False, 'task_name': True}
                            )
                            dev_time_fig.update_layout(xaxis_title='Task Name', yaxis_title='Dev Time (hours)')
                            st.plotly_chart(dev_time_fig)
                    else:
                        st.warning("The selected sheet is empty or could not be read.")
        except Exception as e:
            st.error(f"An error occurred: {e}")
else:
    st.write("You need to authenticate with Google to access your Google Sheets.")
    login()
