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

class OMExtractorSinglePrompt:
    """Single-prompt version of OMExtractor for accuracy comparison"""
    
    def __init__(self):
        self.config = Config()
        self.bedrock_client = self._initialize_bedrock_client()
        
        # Initialize tracking counters
        self.request_count = 0
        self.total_tokens_used = 0
        self.start_time = None
        self.end_time = None
        
        # Log configuration
        print(f"⚙️  Single-Prompt Configuration loaded:")
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
        cleaned = re.sub(r'[^\d.-]', '', str(value))
        if not cleaned or cleaned in ['-', '.']:
            return None
        
        try:
            return float(cleaned)
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
        cleaned = re.sub(r'[^\d.-]', '', str(value))
        if not cleaned or cleaned in ['-', '.']:
            return None
        
        try:
            return float(cleaned)
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
            '%Y-%m-%d',      # 2024-01-15
            '%m/%d/%Y',      # 01/15/2024
            '%m-%d-%Y',      # 01-15-2024
            '%Y/%m/%d',      # 2024/01/15
            '%B %d, %Y',     # January 15, 2024
            '%b %d, %Y',     # Jan 15, 2024
            '%d %B %Y',      # 15 January 2024
            '%d %b %Y',      # 15 Jan 2024
        ]
        
        for fmt in date_formats:
            try:
                return datetime.strptime(str(value).strip(), fmt)
            except ValueError:
                continue
        
        return None
    
    def _validate_and_convert_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate and convert data types according to field requirements"""
        converted_data = {}
        
        # Define field types for conversion
        currency_fields = [
            'sales_price', 'annual_rent', 'numerical_rent_increase'
        ]
        
        number_fields = [
            'year_built_renovated', 'building_sf', 'land_acres', 
            'frequency_of_rent_increase'
        ]
        
        date_fields = [
            'sale_date', 'lease_expiration_date', 'rent_commencement_date'
        ]
        
        # Convert currency fields
        for field in currency_fields:
            if field in data:
                converted_data[field] = self._clean_currency(data[field])
        
        # Convert number fields
        for field in number_fields:
            if field in data:
                converted_data[field] = self._clean_number(data[field])
        
        # Convert date fields
        for field in date_fields:
            if field in data:
                converted_data[field] = self._parse_date(data[field])
        
        # Copy other fields as-is
        for key, value in data.items():
            if key not in converted_data:
                converted_data[key] = value
        
        return converted_data
    
    def _initialize_bedrock_client(self):
        """Initialize AWS Bedrock client"""
        try:
            client = boto3.client(
                'bedrock-runtime',
                region_name=self.config.AWS_REGION
            )
            print("✅ AWS Bedrock client initialized successfully")
            return client
        except Exception as e:
            print(f"❌ Failed to initialize Bedrock client: {e}")
            return None
    
    def read_pdf(self, file_path: str) -> Optional[str]:
        """Read text content from PDF file"""
        try:
            with open(file_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                text = ""
                
                for page_num, page in enumerate(pdf_reader.pages):
                    page_text = page.extract_text()
                    if page_text.strip():
                        text += f"\n--- Page {page_num + 1} ---\n"
                        text += page_text
                
                return text.strip()
        except Exception as e:
            print(f"❌ Error reading PDF: {e}")
            return None
    
    def chunk_text(self, text: str, chunk_size: int = None, overlap: int = None) -> List[str]:
        """Split text into overlapping chunks for processing"""
        if chunk_size is None:
            chunk_size = self.config.CHUNK_SIZE
        if overlap is None:
            overlap = self.config.OVERLAP_SIZE
        
        if len(text) <= chunk_size:
            return [text]
        
        chunks = []
        start = 0
        
        while start < len(text):
            end = start + chunk_size
            
            # Try to break at sentence boundary
            if end < len(text):
                # Look for sentence endings within the last 200 characters
                search_start = max(start + chunk_size - 200, start)
                sentence_end = text.rfind('.', search_start, end)
                if sentence_end > search_start:
                    end = sentence_end + 1
            
            chunk = text[start:end].strip()
            if chunk:
                chunks.append(chunk)
            
            # Move start position with overlap
            start = end - overlap
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
        """
        if not self.config.GEOCODING_ENABLED or not address:
            return None
        
        try:
            # Clean the address
            clean_address = address.strip()
            if not clean_address:
                return None
            
            # Use Nominatim geocoding service
            url = "https://nominatim.openstreetmap.org/search"
            params = {
                'q': clean_address,
                'format': 'json',
                'limit': 1,
                'addressdetails': 1
            }
            headers = {
                'User-Agent': self.config.NOMINATIM_USER_AGENT
            }
            
            response = requests.get(url, params=params, headers=headers, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            if data and len(data) > 0:
                lat = float(data[0]['lat'])
                lon = float(data[0]['lon'])
                return (lat, lon)
            
        except Exception as e:
            print(f"⚠️ Geocoding failed for '{address}': {e}")
        
        return None
    
    def create_single_extraction_prompt(self, text: str) -> str:
        """Create a single comprehensive prompt for all 19 fields"""
        return f"""You are an expert at extracting information from commercial real estate Offering Memorandums (OMs). 

Extract the following 19 fields from the provided text and return them as a JSON object. Follow these formatting rules:

**FORMATTING RULES:**
- **Numerical fields**: Return as decimal numbers only (no $, commas, or text)
- **Date fields**: Return in ISO format (YYYY-MM-DD) for easy Python datetime parsing
- **Text fields**: Return as clean strings
- **Missing fields**: Return null for any field not found

**FIELDS TO EXTRACT:**

**Group 1: Property & Location (5 fields)**
- tenant_name: Name of the tenant/lessee
- property_address: Full property address
- city: City name
- state: State abbreviation (e.g., FL, CA, TX)
- submarket_name: Submarket or area name

**Group 2: Financial Details (6 fields)**
- sales_price: Sales price as decimal number
- annual_rent: Annual rent amount as decimal number
- lease_type: Type of lease (e.g., NNN, Gross, Modified Gross)
- increases: Description of rent increases
- numerical_rent_increase: Rent increase percentage as decimal number
- frequency_of_rent_increase: Years between rent increases as decimal number

**Group 3: Physical Property (4 fields)**
- year_built_renovated: Year built or last renovated as decimal number
- building_sf: Building square footage as decimal number
- land_acres: Land size in acres as decimal number
- landlord_expense_responsibilities: What landlord pays for

**Group 4: Lease Details (4 fields)**
- sale_date: Date of sale in ISO format (YYYY-MM-DD)
- lease_expiration_date: Lease expiration date in ISO format (YYYY-MM-DD)
- guarantor_operator: Guarantor or operator name
- rent_commencement_date: When rent starts in ISO format (YYYY-MM-DD)

**OUTPUT FORMAT:**
Return ONLY a valid JSON object with these exact field names. Do not include any explanatory text.

**TEXT TO ANALYZE:**
{text}

**JSON RESPONSE:**"""
    
    def parse_claude_response(self, response: str) -> Optional[Dict[str, Any]]:
        """Parse Claude's response and extract JSON data"""
        try:
            # Try to find JSON in the response
            json_start = response.find('{')
            json_end = response.rfind('}') + 1
            
            if json_start != -1 and json_end > json_start:
                json_str = response[json_start:json_end]
                return json.loads(json_str)
            else:
                print("No JSON found in response")
                return None
        except json.JSONDecodeError as e:
            print(f"Error parsing JSON: {e}")
            return None
        except Exception as e:
            print(f"Error parsing Claude response: {e}")
            return None
    
    def extract_all_fields_single_prompt(self, text: str) -> Optional[Dict[str, Any]]:
        """Extract all 19 fields using a single comprehensive prompt"""
        prompt = self.create_single_extraction_prompt(text)
        claude_response = self.call_claude(prompt)
        
        if not claude_response:
            return None
        
        parsed_data = self.parse_claude_response(claude_response)
        return parsed_data
    
    def _extract_all_groups_parallel(self, text: str) -> Dict[str, Any]:
        """Extract all fields using single prompt with parallel processing for chunks"""
        # For single prompt, we just call the extraction method directly
        result = self.extract_all_fields_single_prompt(text)
        return result if result else {}
    
    def _extract_all_groups_chunked(self, chunks: List[str]) -> Dict[str, Any]:
        """Extract all fields from chunked text using single prompt approach"""
        combined_data = {}
        
        print(f"🚀 Processing {len(chunks)} chunks simultaneously with single-prompt approach...")
        
        # Process all chunks simultaneously
        with ThreadPoolExecutor(max_workers=len(chunks)) as executor:  # Process all chunks at once
            # Submit all chunk processing tasks
            future_to_chunk = {
                executor.submit(self.extract_all_fields_single_prompt, chunk): i 
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
                if key not in combined and value is not None and value != "":
                    combined[key] = value
        
        return combined
    
    def extract_from_file(self, file_path: str) -> Optional[OMExtractionResult]:
        """Extract information from a PDF file using single-prompt approach"""
        self.start_time = time.time()
        
        print(f"📖 Reading PDF: {file_path}")
        text = self.read_pdf(file_path)
        if not text:
            return None
        
        print(f"📄 Processing document ({len(text):,} characters)...")
        
        # Initialize combined results
        combined_data = {}
        
        # Determine if chunking is needed
        if len(text) <= self.config.CHUNK_SIZE:
            # Process all fields with full text using single prompt
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
        validated_data = self._validate_and_convert_data(combined_data)
        
        # Geocode address if available
        latitude, longitude = None, None
        if self.config.GEOCODING_ENABLED and validated_data.get('property_address'):
            print("🌍 Geocoding property address...")
            coords = self.geocode_address(validated_data['property_address'])
            if coords:
                latitude, longitude = coords
                print(f"✅ Geocoded: {latitude}, {longitude}")
            else:
                print("⚠️ Geocoding failed")
        
        # Create result object
        result = OMExtractionResult(
            # Group 1: Property & Location
            tenant_name=validated_data.get('tenant_name'),
            property_address=validated_data.get('property_address'),
            city=validated_data.get('city'),
            state=validated_data.get('state'),
            submarket_name=validated_data.get('submarket_name'),
            
            # Group 2: Financial Details
            sales_price=validated_data.get('sales_price'),
            annual_rent=validated_data.get('annual_rent'),
            lease_type=validated_data.get('lease_type'),
            increases=validated_data.get('increases'),
            numerical_rent_increase=validated_data.get('numerical_rent_increase'),
            frequency_of_rent_increase=validated_data.get('frequency_of_rent_increase'),
            
            # Group 3: Physical Property
            year_built_renovated=validated_data.get('year_built_renovated'),
            building_sf=validated_data.get('building_sf'),
            land_acres=validated_data.get('land_acres'),
            landlord_expense_responsibilities=validated_data.get('landlord_expense_responsibilities'),
            
            # Group 4: Lease Details
            sale_date=validated_data.get('sale_date'),
            lease_expiration_date=validated_data.get('lease_expiration_date'),
            guarantor_operator=validated_data.get('guarantor_operator'),
            rent_commencement_date=validated_data.get('rent_commencement_date'),
            
            # Geocoding
            latitude=latitude,
            longitude=longitude,
            
            # Metadata
            extraction_timestamp=datetime.now(),
            source_file=Path(file_path).name
        )
        
        self.end_time = time.time()
        print("✅ Extraction completed successfully!")
        
        # Print statistics
        self._print_extraction_stats()
        
        return result
    
    def _print_extraction_stats(self):
        """Print extraction statistics"""
        if self.start_time and self.end_time:
            total_time = self.end_time - self.start_time
            avg_time = total_time / max(self.request_count, 1)
            requests_per_minute = (self.request_count / total_time) * 60 if total_time > 0 else 0
            
            print(f"\n📊 EXTRACTION STATISTICS")
            print(f"   ⏱️  Total Time: {total_time:.2f} seconds")
            print(f"   🔢 API Requests: {self.request_count}")
            print(f"   🪙 Total Tokens: {self.total_tokens_used:,}")
            print(f"   ⚡ Avg Time per Request: {avg_time:.2f}s")
            print(f"   🚀 Requests per Minute: {requests_per_minute:.1f}")
    
    def get_extraction_stats(self) -> Dict[str, Any]:
        """Get extraction statistics"""
        total_time = (self.end_time - self.start_time) if (self.start_time and self.end_time) else 0
        avg_time = total_time / max(self.request_count, 1) if self.request_count > 0 else 0
        requests_per_minute = (self.request_count / total_time) * 60 if total_time > 0 else 0
        
        return {
            'total_time_seconds': total_time,
            'request_count': self.request_count,
            'total_tokens_used': self.total_tokens_used,
            'avg_time_per_request': avg_time,
            'requests_per_minute': requests_per_minute
        }
