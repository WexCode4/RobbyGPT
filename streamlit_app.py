#!/usr/bin/env python3
"""
Streamlit App for OM Extraction and Geocoding
"""

import streamlit as st
import pandas as pd
import tempfile
import os
import sys
from pathlib import Path
from streamlit_pdf_viewer import pdf_viewer
import folium
from streamlit_folium import st_folium
from io import BytesIO

# Add the project root to the path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.OMExtractorSinglePrompt import OMExtractorSinglePrompt

def main():
    st.set_page_config(
        page_title="OM Extractor",
        page_icon="📄",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    st.title("📄 RobbyGPT - OM Extractor")
    st.markdown("Upload an Offering Memorandum PDF to extract information using single-prompt approach")
    
    # Check AWS credentials status
    with st.sidebar:
        st.header("🔐 AWS Status")
        try:
            from config.config import Config
            credentials = Config.get_aws_credentials()
            if credentials['aws_access_key_id'] and credentials['aws_secret_access_key']:
                st.success("✅ AWS Credentials Loaded")
                st.caption("Using Streamlit Secrets")
            else:
                st.warning("⚠️ Using Default AWS Credentials")
                st.caption("IAM Role or Environment Variables")
        except Exception as e:
            st.error(f"❌ Credential Error: {e}")
    
    # Initialize OMExtractor
    if 'extractor' not in st.session_state:
        st.session_state.extractor = OMExtractorSinglePrompt()
    
    # Sidebar for file upload
    with st.sidebar:
        st.header("📁 Upload OM")
        uploaded_file = st.file_uploader(
            "Choose a PDF file",
            type=['pdf'],
            help="Upload an Offering Memorandum PDF file"
        )
               
        if uploaded_file is not None:
            st.success(f"File uploaded: {uploaded_file.name}")
            
            # Extract button
            if st.button("🚀 Extract Information", type="primary"):
                with st.spinner("Extracting information from PDF..."):
                    # Save uploaded file temporarily for processing
                    with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_file:
                        tmp_file.write(uploaded_file.getvalue())
                        tmp_file_path = tmp_file.name
                    
                    try:
                        # Show single-prompt processing status
                        st.info("🚀 Using single-prompt approach - all chunks processed simultaneously...")
                        
                        # Extract information using OMExtractor
                        result = st.session_state.extractor.extract_from_file(tmp_file_path)
                        
                        if result:
                            # Store result in session state
                            st.session_state.extraction_result = result
                            st.session_state.pdf_bytes = uploaded_file.getvalue()
                            st.success("✅ Extraction completed successfully!")
                        else:
                            st.error("❌ Extraction failed. Please check the PDF file.")
                        
                        # Clean up temporary file
                        os.unlink(tmp_file_path)
                        
                    except Exception as e:
                        st.error(f"❌ Error during extraction: {str(e)}")
                        # Clean up temporary file
                        if os.path.exists(tmp_file_path):
                            os.unlink(tmp_file_path)
        
        # Save Data section in sidebar
        if 'extraction_result' in st.session_state:
            st.header("💾 Save Data")
            
            if st.button("💾 Save Data", type="primary"):
                result = st.session_state.extraction_result
                
                # Get the edited data from session state and apply proper formatting
                if 'edited_data' in st.session_state:
                    # Use the edited data from the table
                    edited_df = st.session_state.edited_data
                    
                    # Apply proper formatting to edited data
                    formatted_values = []
                    for index, row in edited_df.iterrows():
                        field_name = row['Field']
                        raw_value = row['Value']
                        
                        # Apply formatting based on field type
                        if field_name in ['Sales Price', 'Annual Rent']:
                            # Remove $ and commas, keep as number
                            if raw_value and raw_value != '':
                                try:
                                    # Remove $ and commas, convert to float
                                    cleaned = str(raw_value).replace('$', '').replace(',', '').replace(' SF', '').replace(' acres', '').replace('%', '').replace(' years', '')
                                    formatted_values.append(str(float(cleaned)) if cleaned else '')
                                except:
                                    formatted_values.append('')
                            else:
                                formatted_values.append('')
                        elif field_name in ['Numerical Rent Increase', 'Frequency of Rent Increase', 'Year Built/Renovated', 'Building SF', 'Land (Acres)']:
                            # Remove units and keep as number
                            if raw_value and raw_value != '':
                                try:
                                    cleaned = str(raw_value).replace(' SF', '').replace(' acres', '').replace('%', '').replace(' years', '')
                                    formatted_values.append(str(float(cleaned)) if cleaned else '')
                                except:
                                    formatted_values.append('')
                            else:
                                formatted_values.append('')
                        elif field_name in ['Sale Date', 'Lease Expiration Date', 'Rent Commencement Date']:
                            # Format dates as MM/DD/YYYY
                            if raw_value and raw_value != '':
                                try:
                                    # Try to parse various date formats and convert to MM/DD/YYYY
                                    from datetime import datetime
                                    date_formats = ['%Y-%m-%d', '%m/%d/%Y', '%m-%d-%Y', '%Y/%m/%d']
                                    for fmt in date_formats:
                                        try:
                                            parsed_date = datetime.strptime(str(raw_value), fmt)
                                            formatted_values.append(parsed_date.strftime('%m/%d/%Y'))
                                            break
                                        except:
                                            continue
                                    else:
                                        formatted_values.append(str(raw_value))
                                except:
                                    formatted_values.append(str(raw_value))
                            else:
                                formatted_values.append('')
                        else:
                            # Keep text fields as-is
                            formatted_values.append(str(raw_value) if raw_value else '')
                    
                    # Create formatted dataframe
                    formatted_df = pd.DataFrame({
                        'Field': edited_df['Field'].tolist(),
                        'Value': formatted_values
                    })
                else:
                    # Fallback to original data if no edits made
                    formatted_df = pd.DataFrame({
                        'Field': [
                            'Tenant Name', 'Property Address', 'City', 'State', 'Submarket Name',
                            'Sales Price', 'Annual Rent', 'Lease Type', 'Increases', 'Numerical Rent Increase', 'Frequency of Rent Increase',
                            'Year Built/Renovated', 'Building SF', 'Land (Acres)', 'Landlord Expense Responsibilities',
                            'Sale Date', 'Lease Expiration Date', 'Guarantor (Operator)', 'Rent Commencement Date',
                            'Latitude', 'Longitude'
                        ],
                        'Value': [
                            str(result.tenant_name) if result.tenant_name is not None else '',
                            str(result.property_address) if result.property_address is not None else '',
                            str(result.city) if result.city is not None else '',
                            str(result.state) if result.state is not None else '',
                            str(result.submarket_name) if result.submarket_name is not None else '',
                            str(result.sales_price) if result.sales_price is not None else '',
                            str(result.annual_rent) if result.annual_rent is not None else '',
                            str(result.lease_type) if result.lease_type is not None else '',
                            str(result.increases) if result.increases is not None else '',
                            str(result.numerical_rent_increase) if result.numerical_rent_increase is not None else '',
                            str(result.frequency_of_rent_increase) if result.frequency_of_rent_increase is not None else '',
                            str(result.year_built_renovated) if result.year_built_renovated is not None else '',
                            str(result.building_sf) if result.building_sf is not None else '',
                            str(result.land_acres) if result.land_acres is not None else '',
                            str(result.landlord_expense_responsibilities) if result.landlord_expense_responsibilities is not None else '',
                            result.sale_date.strftime('%m/%d/%Y') if result.sale_date is not None else '',
                            result.lease_expiration_date.strftime('%m/%d/%Y') if result.lease_expiration_date is not None else '',
                            str(result.guarantor_operator) if result.guarantor_operator is not None else '',
                            result.rent_commencement_date.strftime('%m/%d/%Y') if result.rent_commencement_date is not None else '',
                            str(result.latitude) if result.latitude is not None else '',
                            str(result.longitude) if result.longitude is not None else ''
                        ]
                    })
                
                # Create Excel file in memory
                output = BytesIO()
                
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    # Transpose the data so fields are column headers
                    transposed_df = formatted_df.set_index('Field').T
                    transposed_df.to_excel(writer, sheet_name='OM_Data', index=False)
                    
                    # Add metadata sheet
                    metadata_df = pd.DataFrame({
                        'Field': ['Source File', 'Extraction Date', 'API Requests', 'Processing Time'],
                        'Value': [
                            result.source_file,
                            result.extraction_date.strftime('%m/%d/%Y %H:%M:%S'),
                            result.request_count if hasattr(result, 'request_count') else 'N/A',
                            f"{result.total_time_seconds:.2f}s" if hasattr(result, 'total_time_seconds') else 'N/A'
                        ]
                    })
                    metadata_df.to_excel(writer, sheet_name='Metadata', index=False)
                
                output.seek(0)
                filename = f"OM_Extraction_{result.source_file.replace('.pdf', '')}.xlsx"
                
                # Store file data in session state
                st.session_state.excel_file_data = output.getvalue()
                st.session_state.excel_filename = filename
                st.session_state.show_download = True
                
                st.success("✅ Data ready for download!")
                st.rerun()
        
        # Show download button if data is ready
        if st.session_state.get('show_download', False) and 'excel_file_data' in st.session_state:
            st.download_button(
                label="⬇️ Download Excel File",
                data=st.session_state.excel_file_data,
                file_name=st.session_state.excel_filename,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="download_excel"
            )
    
    # Main content area
    if 'extraction_result' in st.session_state and 'pdf_bytes' in st.session_state:
        result = st.session_state.extraction_result
        
        # Create two columns for data table and PDF viewer
        col1, col2 = st.columns([1, 1])
        
        with col1:
            st.header("📊 Extracted Data")
            
            # Convert result to DataFrame with fields ordered by group
            data_dict = {
                'Field': [
                    # Group 1: Property & Location (5 fields)
                    'Tenant Name', 'Property Address', 'City', 'State', 'Submarket Name',
                    # Group 2: Financial Details (6 fields)
                    'Sales Price', 'Annual Rent', 'Lease Type', 'Increases', 'Numerical Rent Increase', 'Frequency of Rent Increase',
                    # Group 3: Physical Property (4 fields)
                    'Year Built/Renovated', 'Building SF', 'Land (Acres)', 'Landlord Expense Responsibilities',
                    # Group 4: Lease Details (4 fields)
                    'Sale Date', 'Lease Expiration Date', 'Guarantor (Operator)', 'Rent Commencement Date',
                    # Geocoding (2 fields)
                    'Latitude', 'Longitude'
                ],
                'Value': [
                    # Group 1: Property & Location
                    str(result.tenant_name) if result.tenant_name is not None else '',
                    str(result.property_address) if result.property_address is not None else '',
                    str(result.city) if result.city is not None else '',
                    str(result.state) if result.state is not None else '',
                    str(result.submarket_name) if result.submarket_name is not None else '',
                    # Group 2: Financial Details
                    f"${result.sales_price:,.2f}" if result.sales_price is not None else '',
                    f"${result.annual_rent:,.2f}" if result.annual_rent is not None else '',
                    str(result.lease_type) if result.lease_type is not None else '',
                    str(result.increases) if result.increases is not None else '',
                    f"{result.numerical_rent_increase:.1f}%" if result.numerical_rent_increase is not None else '',
                    f"{result.frequency_of_rent_increase:.1f} years" if result.frequency_of_rent_increase is not None else '',
                    # Group 3: Physical Property
                    f"{result.year_built_renovated:.0f}" if result.year_built_renovated is not None else '',
                    f"{result.building_sf:,.0f} SF" if result.building_sf is not None else '',
                    f"{result.land_acres:.2f} acres" if result.land_acres is not None else '',
                    str(result.landlord_expense_responsibilities) if result.landlord_expense_responsibilities is not None else '',
                    # Group 4: Lease Details
                    result.sale_date.strftime('%Y-%m-%d') if result.sale_date is not None else '',
                    result.lease_expiration_date.strftime('%Y-%m-%d') if result.lease_expiration_date is not None else '',
                    str(result.guarantor_operator) if result.guarantor_operator is not None else '',
                    result.rent_commencement_date.strftime('%Y-%m-%d') if result.rent_commencement_date is not None else '',
                    # Geocoding
                    f"{result.latitude:.6f}" if result.latitude is not None else '',
                    f"{result.longitude:.6f}" if result.longitude is not None else ''
                ]
            }
            
            df = pd.DataFrame(data_dict)
            
            # Display editable matrix with all fields
            edited_df = st.data_editor(
                df, 
                height=800, 
                hide_index=True,
                num_rows="fixed",
                use_container_width=True,
                key="data_editor"
            )
            
            # Store the edited data in session state for export
            st.session_state.edited_data = edited_df
            
            
            # Display source file info
            st.info(f"📄 Source: {result.source_file}")
            st.info(f"🕒 Extracted: {result.extraction_date.strftime('%Y-%m-%d %H:%M:%S')}")
            
            # Display extraction statistics if available
            if hasattr(st.session_state.extractor, 'get_extraction_stats'):
                stats = st.session_state.extractor.get_extraction_stats()
                if stats['request_count'] > 0:
                    st.success(f"📊 Extraction Stats: {stats['request_count']} API requests, {stats['total_tokens_used']:,} tokens, {stats['total_time_seconds']:.1f}s total")
        
        with col2:
            st.header("📖 PDF Viewer")
            
            # Display PDF using streamlit-pdf-viewer
            pdf_viewer(
                st.session_state.pdf_bytes,
                width=800,
                height=800
            )
        
        # Map section at the bottom
        st.header("🗺️ Property Location")
        
        if result.latitude and result.longitude:
            # Create folium map
            m = folium.Map(
                location=[result.latitude, result.longitude],
                zoom_start=15,
                tiles='OpenStreetMap'
            )
            
            # Add marker for the property
            folium.Marker(
                [result.latitude, result.longitude],
                popup=f"Property: {result.property_address or 'Address not available'}",
                tooltip="Click for property details",
                icon=folium.Icon(color='red', icon='info-sign')
            ).add_to(m)
            
            # Display the map
            st_folium(m, width=1800, height=600)
            
            st.success(f"📍 Coordinates: {result.latitude:.6f}, {result.longitude:.6f}")
        else:
            st.warning("⚠️ No coordinates available. Geocoding may have failed or was disabled.")
            
            # Show address for reference
            if result.property_address:
                st.info(f"📍 Address: {result.property_address}")
    
    else:
        # Welcome message when no file is uploaded
        st.info("👈 Please upload a PDF file using the sidebar to get started!")
        
        # Placeholder for layout
        col1, col2 = st.columns([1, 1])
        
        with col1:
            st.header("📊 Extracted Data")
            st.info("Data will appear here after extraction")
        
        with col2:
            st.header("📖 PDF Viewer")
            st.info("PDF will appear here after upload")
        
        st.header("🗺️ Property Location")
        st.info("Map will appear here after extraction and geocoding")

if __name__ == "__main__":
    main() 