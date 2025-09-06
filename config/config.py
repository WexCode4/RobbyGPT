import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class Config:
    # AWS Bedrock Configuration
    AWS_REGION = os.getenv('AWS_REGION', 'us-east-1')
    BEDROCK_MODEL_ID = os.getenv('BEDROCK_MODEL_ID', 'anthropic.claude-3-sonnet-20240229-v1:0')
    # BEDROCK_MODEL_ID = os.getenv('BEDROCK_MODEL_ID', 'anthropic.claude-3-5-sonnet-20241022-v2:0')
    
    # File paths
    OM_REPO_PATH = os.getenv('OM_REPO_PATH', 'OM_Repo')
    
    # API Configuration
    MAX_TOKENS = int(os.getenv('MAX_TOKENS', '4096'))
    TEMPERATURE = float(os.getenv('TEMPERATURE', '0.1'))
    
    # Chunking Configuration
    CHUNK_SIZE = int(os.getenv('CHUNK_SIZE', '10000'))  # Increased for better context
    OVERLAP_SIZE = int(os.getenv('OVERLAP_SIZE', '500'))  # Increased overlap for better continuity
    
    # Processing Configuration
    ENABLE_CHUNKING = os.getenv('ENABLE_CHUNKING', 'true').lower() == 'true'
    MIN_CHUNK_SIZE = int(os.getenv('MIN_CHUNK_SIZE', '1000'))  # Minimum chunk size
    MAX_CHUNKS = int(os.getenv('MAX_CHUNKS', '10'))  # Maximum number of chunks to process
    
    # Geocoding Configuration
    GEOCODING_ENABLED = os.getenv('GEOCODING_ENABLED', 'true').lower() == 'true'
    NOMINATIM_USER_AGENT = os.getenv('NOMINATIM_USER_AGENT', 'RobbyGPT/1.0')
    
    # Parallel Processing Configuration (Always Enabled)
    PARALLEL_EXTRACTION = True  # Always use parallel processing
    MAX_WORKERS = int(os.getenv('MAX_WORKERS', '4'))  # Reduced to prevent throttling
    
    # Streamlit Secrets Support
    @staticmethod
    def get_aws_credentials():
        """Get AWS credentials from Streamlit secrets or environment variables"""
        try:
            import streamlit as st
            # Try Streamlit secrets first
            if hasattr(st, 'secrets') and 'AWS_ACCESS_KEY_ID' in st.secrets:
                return {
                    'aws_access_key_id': st.secrets['AWS_ACCESS_KEY_ID'],
                    'aws_secret_access_key': st.secrets['AWS_SECRET_ACCESS_KEY'],
                    'aws_region': st.secrets.get('AWS_REGION', Config.AWS_REGION)
                }
        except:
            pass
        
        # Fallback to environment variables
        return {
            'aws_access_key_id': os.getenv('AWS_ACCESS_KEY_ID'),
            'aws_secret_access_key': os.getenv('AWS_SECRET_ACCESS_KEY'),
            'aws_region': os.getenv('AWS_REGION', Config.AWS_REGION)
        }