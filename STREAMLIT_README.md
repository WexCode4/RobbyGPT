# Streamlit OM Extractor App

A simple Streamlit application for extracting information from Offering Memorandum PDFs and geocoding the property addresses.

## Features

- **File Upload**: Upload OM PDFs through the sidebar
- **Data Extraction**: Automatically extract 18 fields using the OMExtractor class
- **Editable Data**: View and edit extracted data in an interactive table
- **PDF Viewer**: Scroll through the uploaded PDF document
- **Interactive Map**: View the property location on an interactive Folium map using extracted coordinates

## Installation

1. Install the required dependencies:
```bash
pip install -r streamlit_requirements.txt
```

2. Make sure you have the main project dependencies installed:
```bash
pip install -r requirements.txt
```

## Configuration

Set up your environment variables in a `.env` file:
```bash
# AWS Bedrock Configuration
AWS_REGION=us-east-1
BEDROCK_MODEL_ID=anthropic.claude-3-sonnet-20240229-v1:0

# Geocoding Configuration
GEOCODING_ENABLED=true
NOMINATIM_USER_AGENT=RobbyGPT/1.0
```

## Running the App

1. Navigate to the project directory:
```bash
cd RobbyGPT
```

2. Run the Streamlit app:
```bash
streamlit run streamlit_app.py
```

3. Open your browser and go to the URL shown in the terminal (usually `http://localhost:8501`)

## Usage

1. **Upload PDF**: Use the sidebar to upload an OM PDF file
2. **Extract Data**: Click the "Extract Information" button to process the PDF
3. **Review Data**: View the extracted information in the editable table
4. **View PDF**: Scroll through the PDF document on the right side
5. **See Location**: View the property location on the interactive Folium map at the bottom

## Layout

- **Left Sidebar**: File upload and extraction controls
- **Main Area**: 
  - Left: Extracted data table (editable)
  - Right: PDF viewer
- **Bottom**: Interactive Folium map showing property location with markers and popups

## Map Features

- **Interactive Folium Maps**: More interactive than basic Streamlit maps
- **Property Markers**: Red info markers with property details
- **Clickable Popups**: Click markers to see property information
- **Zoom Controls**: Standard map zoom and pan functionality
- **OpenStreetMap Tiles**: Free, high-quality map tiles

## Error Handling

- The app gracefully handles extraction failures
- Geocoding failures are displayed as warnings
- Temporary files are automatically cleaned up
- User-friendly error messages for common issues

## Notes

- The app processes PDFs directly from upload (no permanent storage)
- Data is not persisted between sessions
- Uses Nominatim (OpenStreetMap) for free geocoding
- Includes rate limiting for geocoding requests 