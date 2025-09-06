import boto3
import json
import PyPDF2
import os
import sys
import requests
import time
import re
from typing import Optional, Dict, Any, List, Tuple
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# Add the project root to the path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.config import Config
from src.models import OMExtractionResult

class OMExtractor:
    """Main class for extracting information from Offering Memorandums"""
    
    def __init__(self):
        self.config = Config()
        self.bedrock_client = self._initialize_bedrock_client()
        
        # Initialize tracking counters
        self.request_count = 0
        self.total_tokens_used = 0
        self.start_time = None
        self.end_time = None
        
        # Log configuration
        print(f"⚙️  Configuration loaded:")
        print(f"   - Model: {self.config.BEDROCK_MODEL_ID}")
        print(f"   - Max Tokens: {self.config.MAX_TOKENS}")
        print(f"   - Temperature: {self.config.TEMPERATURE}")
        print(f"   - Parallel Processing: ✅ Always Enabled")
        print(f"   - Max Workers: {self.config.MAX_WORKERS}")
    
    def _clean_currency(self, value) -> Optional[float]:
        """Convert currency string to decimal number"""
        if value is None or (isinstance(value, str) and value.lower() in ['null', 'none', '']):
            return None
        
        # If already a number, return it
        if isinstance(value, (int, float)):
            return float(value)
        
        # Remove all non-numeric characters except decimal point
        cleaned = re.sub(r'[^\d.]', '', str(value))
        try:
            return float(cleaned) if cleaned else None
        except ValueError:
            return None
    
    def _clean_number(self, value) -> Optional[float]:
        """Convert string to decimal number"""
        if value is None or (isinstance(value, str) and value.lower() in ['null', 'none', '']):
            return None
        
        # If already a number, return it
        if isinstance(value, (int, float)):
            return float(value)
        
        # Remove all non-numeric characters except decimal point
        cleaned = re.sub(r'[^\d.]', '', str(value))
        try:
            return float(cleaned) if cleaned else None
        except ValueError:
            return None
    
    def _parse_date(self, value) -> Optional[datetime]:
        """Parse date string to datetime object"""
        if value is None or (isinstance(value, str) and value.lower() in ['null', 'none', '']):
            return None
        
        # If already a datetime, return it
        if isinstance(value, datetime):
            return value
        
        # Common date formats to try
        date_formats = [
            '%Y-%m-%d',      # ISO format
            '%m/%d/%Y',      # MM/DD/YYYY
            '%m-%d-%Y',      # MM-DD-YYYY
            '%B %d, %Y',     # Month DD, YYYY
            '%b %d, %Y',     # Mon DD, YYYY
            '%Y',            # Just year
        ]
        
        for fmt in date_formats:
            try:
                return datetime.strptime(str(value).strip(), fmt)
            except ValueError:
                continue
        
        return None
    
    def _validate_and_convert_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate and convert extracted data to proper types"""
        converted = {}
        
        for key, value in data.items():
            if value is None or value == "null":
                converted[key] = None
                continue
            
            # Group 1: Property & Location (strings)
            if key in ['tenant_name', 'property_address', 'city', 'state', 'submarket_name']:
                converted[key] = str(value).strip() if value else None
            
            # Group 2: Financial Details
            elif key in ['sales_price', 'annual_rent', 'numerical_rent_increase', 'frequency_of_rent_increase']:
                converted[key] = self._clean_currency(value) if key in ['sales_price', 'annual_rent'] else self._clean_number(value)
            elif key in ['lease_type', 'increases']:
                converted[key] = str(value).strip() if value else None
            
            # Group 3: Physical Property
            elif key in ['year_built_renovated', 'building_sf', 'land_acres']:
                converted[key] = self._clean_number(value)
            elif key == 'landlord_expense_responsibilities':
                converted[key] = str(value).strip() if value else None
            
            # Group 4: Lease Details
            elif key in ['sale_date', 'lease_expiration_date', 'rent_commencement_date']:
                converted[key] = self._parse_date(value)
            elif key == 'guarantor_operator':
                converted[key] = str(value).strip() if value else None
            
            # Geocoding and other fields
            elif key in ['latitude', 'longitude']:
                converted[key] = self._clean_number(value)
            else:
                converted[key] = value
        
        return converted
        
    def _initialize_bedrock_client(self):
        """Initialize AWS Bedrock client"""
        try:
            return boto3.client(
                service_name='bedrock-runtime',
                region_name=self.config.AWS_REGION
            )
        except Exception as e:
            print(f"Error initializing Bedrock client: {e}")
            return None
    
    def read_pdf(self, file_path: str) -> Optional[str]:
        """Extract text from PDF file"""
        try:
            with open(file_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                text = ""
                for page in pdf_reader.pages:
                    text += page.extract_text() + "\n"
                return text
        except Exception as e:
            print(f"Error reading PDF {file_path}: {e}")
            return None
    
    def chunk_text(self, text: str, chunk_size: int = None, overlap: int = None) -> List[str]:
        """
        Split text into overlapping chunks for processing large documents
        
        Args:
            text: The full text to chunk
            chunk_size: Size of each chunk (defaults to config)
            overlap: Overlap between chunks (defaults to config)
        
        Returns:
            List of text chunks
        """
        if chunk_size is None:
            chunk_size = self.config.CHUNK_SIZE
        if overlap is None:
            overlap = self.config.OVERLAP_SIZE
            
        chunks = []
        start = 0
        
        while start < len(text):
            end = start + chunk_size
            chunk = text[start:end]
            chunks.append(chunk)
            
            # Move start position, accounting for overlap
            start = end - overlap
            
            # Ensure we don't get stuck in infinite loop
            if start >= len(text):
                break
                
        print(f"📄 Split document into {len(chunks)} chunks (size: {chunk_size}, overlap: {overlap})")
        return chunks
    
    def call_claude(self, prompt: str) -> Optional[str]:
        """Make API call to Claude via AWS Bedrock with rate limiting and tracking"""
        if not self.bedrock_client:
            print("Bedrock client not initialized")
            return None

        # Increment request counter
        self.request_count += 1
        request_start_time = time.time()

        # Add delay before request to prevent throttling
        time.sleep(0.2)

        try:
            body = json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": self.config.MAX_TOKENS,
                "temperature": self.config.TEMPERATURE,
                "messages": [
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            })

            response = self.bedrock_client.invoke_model(
                modelId=self.config.BEDROCK_MODEL_ID,
                body=body
            )

            response_body = json.loads(response.get('body').read())

            # Track token usage if available
            if 'usage' in response_body:
                usage = response_body['usage']
                input_tokens = usage.get('input_tokens', 0)
                output_tokens = usage.get('output_tokens', 0)
                self.total_tokens_used += input_tokens + output_tokens

            # Calculate request time
            request_time = time.time() - request_start_time

            return response_body['content'][0]['text']

        except Exception as e:
            print(f"❌ Error calling Claude API (Request #{self.request_count}): {e}")
            # Add longer delay on error to help with rate limiting
            time.sleep(1)
            return None
    
    def geocode_address(self, address: str) -> Optional[Tuple[float, float]]:
        """
        Convert address to latitude and longitude coordinates using Nominatim
        
        Args:
            address: Property address string
            
        Returns:
            Tuple of (latitude, longitude) or None if geocoding fails
        """
        if not self.config.GEOCODING_ENABLED or not address:
            return None
            
        try:
            url = "https://nominatim.openstreetmap.org/search"
            params = {
                'q': address,
                'format': 'json',
                'limit': 1
            }
            
            headers = {
                'User-Agent': self.config.NOMINATIM_USER_AGENT
            }
            
            response = requests.get(url, params=params, headers=headers, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            if data:
                return (float(data[0]['lat']), float(data[0]['lon']))
            
            return None
            
        except Exception as e:
            print(f"Geocoding error: {e}")
            return None
    
    def create_property_location_prompt(self, text: str, chunk_info: str = "") -> str:
        """Create a prompt for extracting property and location information"""
        return f"""
        You are an expert at analyzing real estate Offering Memorandums (OMs). 
        Please extract ONLY the following 5 specific pieces of information from the provided OM text and return it as a JSON object:
        
        1. Tenant Name - The name of the tenant/lessee
        2. Property Address - The full property address
        3. City - The city where the property is located
        4. State - The state where the property is located
        5. Submarket Name - The submarket or area name
        
        {chunk_info}
        
        OM Text:
        {text}
        
        Please return ONLY a valid JSON object with this exact structure:
        {{
            "tenant_name": "tenant name or null",
            "property_address": "full property address or null",
            "city": "city name or null",
            "state": "state name or null",
            "submarket_name": "submarket name or null"
        }}
        
        If any information is not found in this text chunk, use null for those fields.
        Be very precise and only extract the exact information requested.
        """
    
    def create_financial_prompt(self, text: str, chunk_info: str = "") -> str:
        """Create a prompt for extracting financial information"""
        return f"""
        You are an expert at analyzing real estate Offering Memorandums (OMs). 
        Please extract ONLY the following 6 specific pieces of information from the provided OM text and return it as a JSON object:
        
        1. Sales Price - The price the property sold for (return as decimal number only, no $ or commas)
        2. Annual Rent - The annual rental amount (return as decimal number only, no $ or commas)
        3. Lease Type - Type of lease (e.g., NNN, Gross, Modified Gross)
        4. Increases - Rent increase description (e.g., "3% annually", "5% every 5 years")
        5. Numerical Rent Increase - The percentage value of rent increase (return as decimal number only)
        6. Frequency of Rent Increase - The number of years between rent increases (return as decimal number only)
        
        {chunk_info}
        
        OM Text:
        {text}
        
        Please return ONLY a valid JSON object with this exact structure:
        {{
            "sales_price": 1833000.00,
            "annual_rent": 110000.00,
            "lease_type": "NNN or null",
            "increases": "rent increase description or null",
            "numerical_rent_increase": 3.0,
            "frequency_of_rent_increase": 1.0
        }}
        
        IMPORTANT FORMATTING RULES:
        - Return all monetary amounts as decimal numbers only (no $, commas, or text)
        - Return all percentages as decimal numbers only (no % symbol)
        - Return all time periods as decimal numbers only (no "years" text)
        - If any information is not found, use null for those fields
        
        Be very precise and only extract the exact information requested.
        """
    
    def create_property_details_prompt(self, text: str, chunk_info: str = "") -> str:
        """Create a prompt for extracting physical property information"""
        return f"""
        You are an expert at analyzing real estate Offering Memorandums (OMs). 
        Please extract ONLY the following 4 specific pieces of information from the provided OM text and return it as a JSON object:
        
        1. Year Built/Renovated - Year the building was built or last renovated (return as decimal number only)
        2. Building SF - Building square footage (return as decimal number only)
        3. Land (Acres) - Land size in acres (return as decimal number only)
        4. Landlord Expense Responsibilities - What expenses the landlord is responsible for
        
        {chunk_info}
        
        OM Text:
        {text}
        
        Please return ONLY a valid JSON object with this exact structure:
        {{
            "year_built_renovated": 2015.0,
            "building_sf": 2500.0,
            "land_acres": 0.5,
            "landlord_expense_responsibilities": "landlord expense description or null"
        }}
        
        IMPORTANT FORMATTING RULES:
        - Return all measurements as decimal numbers only (no units or text)
        - Return years as decimal numbers only (no "year" text)
        - If any information is not found, use null for those fields
        
        Be very precise and only extract the exact information requested.
        """
    
    def create_lease_details_prompt(self, text: str, chunk_info: str = "") -> str:
        """Create a prompt for extracting lease information"""
        return f"""
        You are an expert at analyzing real estate Offering Memorandums (OMs). 
        Please extract ONLY the following 4 specific pieces of information from the provided OM text and return it as a JSON object:
        
        1. Sale Date - The date of sale or transaction date (return in YYYY-MM-DD format)
        2. Lease Expiration Date - When the lease expires (return in YYYY-MM-DD format)
        3. Guarantor (Operator) - The guarantor or operator name
        4. Rent Commencement Date - When rent payments begin (return in YYYY-MM-DD format)
        
        {chunk_info}
        
        OM Text:
        {text}
        
        Please return ONLY a valid JSON object with this exact structure:
        {{
            "sale_date": "2024-08-01",
            "lease_expiration_date": "2034-07-31",
            "guarantor_operator": "guarantor name or null",
            "rent_commencement_date": "2024-08-01"
        }}
        
        IMPORTANT FORMATTING RULES:
        - Return all dates in YYYY-MM-DD format only
        - If only year is available, use YYYY-01-01 format
        - If any information is not found, use null for those fields
        
        Be very precise and only extract the exact information requested.
        """
    
    def parse_claude_response(self, response: str) -> Optional[Dict[str, Any]]:
        """Parse Claude's JSON response"""
        try:
            # Find JSON in the response (in case there's extra text)
            start = response.find('{')
            end = response.rfind('}') + 1
            if start != -1 and end != 0:
                json_str = response[start:end]
                return json.loads(json_str)
            return None
        except Exception as e:
            print(f"Error parsing Claude response: {e}")
            return None
    
    def extract_property_location(self, text: str) -> Optional[Dict[str, Any]]:
        """Extract property and location information"""
        prompt = self.create_property_location_prompt(text)
        claude_response = self.call_claude(prompt)
        
        if not claude_response:
            return None
        
        parsed_data = self.parse_claude_response(claude_response)
        return parsed_data
    
    def extract_financial_details(self, text: str) -> Optional[Dict[str, Any]]:
        """Extract financial information"""
        prompt = self.create_financial_prompt(text)
        claude_response = self.call_claude(prompt)
        
        if not claude_response:
            return None
        
        parsed_data = self.parse_claude_response(claude_response)
        return parsed_data
    
    def extract_property_details(self, text: str) -> Optional[Dict[str, Any]]:
        """Extract physical property information"""
        prompt = self.create_property_details_prompt(text)
        claude_response = self.call_claude(prompt)
        
        if not claude_response:
            return None
        
        parsed_data = self.parse_claude_response(claude_response)
        return parsed_data
    
    def extract_lease_details(self, text: str) -> Optional[Dict[str, Any]]:
        """Extract lease information"""
        prompt = self.create_lease_details_prompt(text)
        claude_response = self.call_claude(prompt)
        
        if not claude_response:
            return None
        
        parsed_data = self.parse_claude_response(claude_response)
        return parsed_data
    
    def combine_chunk_results(self, chunk_results: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """
        Combine results from multiple chunks into a single result
        
        Args:
            chunk_results: List of parsed data from each chunk
        
        Returns:
            Combined result with first non-null value for each field
        """
        if not chunk_results:
            return None
        
        # Initialize combined result structure with all 16 fields
        combined = {
            "tenant_name": None,
            "submarket_name": None,
            "property_address": None,
            "city": None,
            "state": None,
            "sale_date": None,
            "sales_price": None,
            "annual_rent": None,
            "lease_expiration_date": None,
            "guarantor_operator": None,
            "lease_type": None,
            "landlord_expense_responsibilities": None,
            "year_built_renovated": None,
            "building_sf": None,
            "land_acres": None,
            "increases": None,
            "latitude": None,
            "longitude": None
        }
        
        # Simple strategy: take the first non-null value for each field
        for chunk_result in chunk_results:
            if not chunk_result:
                continue
                
            # For each field, use the first non-null value found
            for field in combined.keys():
                if field in chunk_result and chunk_result[field] and chunk_result[field] != "null":
                    if combined[field] is None or combined[field] == "null":
                        combined[field] = chunk_result[field]
        
        print(f"🔗 Combined results from {len(chunk_results)} chunks")
        return combined
    
    def extract_from_file(self, filename: str) -> Optional[OMExtractionResult]:
        """Main method to extract information from an OM file using hybrid approach"""
        # Reset tracking for new extraction
        self.request_count = 0
        self.total_tokens_used = 0
        self.start_time = time.time()
        
        # Handle both absolute paths (from Streamlit) and relative paths (from OM_Repo)
        if os.path.isabs(filename):
            file_path = Path(filename)
        else:
            file_path = Path(self.config.OM_REPO_PATH) / filename
        
        if not file_path.exists():
            print(f"File not found: {file_path}")
            return None
        
        # Read PDF
        print(f"📖 Reading PDF: {filename}")
        text = self.read_pdf(str(file_path))
        if not text:
            return None
        
        print(f"📄 Processing document ({len(text):,} characters)...")
        
        # Initialize combined results
        combined_data = {}
        
        # Determine if chunking is needed
        if len(text) <= self.config.CHUNK_SIZE:
            # Process all groups with full text using parallel processing
            combined_data.update(self._extract_all_groups_parallel(text))
        else:
            # Split into chunks and process each chunk in parallel
            chunks = self.chunk_text(text)
            combined_data = self._extract_all_groups_chunked(chunks)
        
        if not combined_data:
            print("❌ No valid results from extraction")
            return None
        
        # Validate and convert data types
        print("🔧 Validating and converting data types...")
        combined_data = self._validate_and_convert_data(combined_data)
        
        # Add geocoding if we have a property address
        if combined_data.get('property_address') and self.config.GEOCODING_ENABLED:
            print(f"🗺️ Geocoding address: {combined_data['property_address']}")
            coordinates = self.geocode_address(combined_data['property_address'])
            
            if coordinates:
                combined_data['latitude'] = coordinates[0]
                combined_data['longitude'] = coordinates[1]
                print(f"✅ Geocoding successful: {coordinates[0]:.6f}, {coordinates[1]:.6f}")
            else:
                print("❌ Geocoding failed, coordinates will be null")
                # Add a small delay to respect rate limits
                time.sleep(1)
        
        # Create structured result
        try:
            result = OMExtractionResult(
                **combined_data,
                source_file=filename
            )
            
            # Calculate final timing and statistics
            self.end_time = time.time()
            total_time = self.end_time - self.start_time
            
            print("✅ Extraction completed successfully!")
            print(f"\n📊 EXTRACTION STATISTICS")
            print(f"   ⏱️  Total Time: {total_time:.2f} seconds")
            print(f"   🔢 API Requests: {self.request_count}")
            print(f"   🪙 Total Tokens: {self.total_tokens_used:,}")
            if self.request_count > 0:
                print(f"   ⚡ Avg Time per Request: {total_time/self.request_count:.2f}s")
                print(f"   🚀 Requests per Minute: {60 * self.request_count / total_time:.1f}")
            
            return result
        except Exception as e:
            print(f"Error creating extraction result: {e}")
            return None
    
    def _extract_all_groups(self, text: str) -> Dict[str, Any]:
        """Extract all groups from a single text using parallel processing"""
        return self._extract_all_groups_parallel(text)
    
    def _extract_all_groups_parallel(self, text: str) -> Dict[str, Any]:
        """Extract all groups in parallel for faster processing"""
        combined_data = {}

        # Define extraction tasks
        extraction_tasks = [
            ("property_location", self.extract_property_location),
            ("financial_details", self.extract_financial_details),
            ("property_details", self.extract_property_details),
            ("lease_details", self.extract_lease_details)
        ]

        # Execute extractions in parallel with reduced concurrency to prevent throttling
        with ThreadPoolExecutor(max_workers=2) as executor:  # Reduced from 4 to 2
            # Submit all tasks
            future_to_group = {
                executor.submit(extract_method, text): group_name
                for group_name, extract_method in extraction_tasks
            }

            # Collect results as they complete
            for future in as_completed(future_to_group):
                group_name = future_to_group[future]
                try:
                    result = future.result()
                    if result:
                        combined_data.update(result)
                except Exception as e:
                    print(f"❌ {group_name} error: {e}")

        return combined_data
    
    def _extract_all_groups_chunked(self, chunks: List[str]) -> Dict[str, Any]:
        """Extract all groups from chunked text using parallel processing"""
        combined_data = {}
        
        print(f"🚀 Processing {len(chunks)} chunks with parallel processing...")
        
        # Process chunks with reduced concurrency to prevent throttling
        with ThreadPoolExecutor(max_workers=2) as executor:  # Reduced concurrency
            # Submit all chunk processing tasks
            future_to_chunk = {
                executor.submit(self._extract_all_groups_parallel, chunk): i 
                for i, chunk in enumerate(chunks)
            }
            
            # Collect results as they complete
            chunk_results = []
            for future in as_completed(future_to_chunk):
                chunk_index = future_to_chunk[future]
                try:
                    result = future.result()
                    if result:
                        chunk_results.append(result)
                except Exception as e:
                    print(f"❌ Chunk {chunk_index + 1} error: {e}")
        
        # Combine results from all chunks (take first non-null value for each field)
        if chunk_results:
            combined_data = self._combine_group_results(chunk_results)
            print(f"✅ Combined results from {len(chunk_results)} chunks")
        else:
            print("❌ No valid results from any chunks")
        
        return combined_data
    
    def _combine_group_results(self, group_results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Combine results from multiple chunks for a single group"""
        if not group_results:
            return {}
        
        combined = {}
        
        # For each field, take the first non-null value
        for result in group_results:
            for key, value in result.items():
                if key not in combined and value is not None and value != "null":
                    combined[key] = value
        
        return combined
    
    def get_extraction_stats(self) -> Dict[str, Any]:
        """Get current extraction statistics"""
        total_time = None
        if self.start_time and self.end_time:
            total_time = self.end_time - self.start_time
        elif self.start_time:
            total_time = time.time() - self.start_time
        
        return {
            'request_count': self.request_count,
            'total_tokens_used': self.total_tokens_used,
            'total_time_seconds': total_time,
            'avg_time_per_request': total_time / self.request_count if self.request_count > 0 and total_time else None,
            'requests_per_minute': 60 * self.request_count / total_time if total_time and total_time > 0 else None
        }
    
    def list_available_oms(self) -> list:
        """List all OM files in the repository"""
        om_path = Path(self.config.OM_REPO_PATH)
        if not om_path.exists():
            return []
        
        return [f.name for f in om_path.iterdir() if f.suffix.lower() == '.pdf']
