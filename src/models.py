from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

class OMExtractionResult(BaseModel):
    """Complete extraction result with all requested fields using hybrid categorized approach"""
    
    # Group 1: Property & Location (5 fields)
    tenant_name: Optional[str] = Field(None, description="Tenant name")
    property_address: Optional[str] = Field(None, description="Property address")
    city: Optional[str] = Field(None, description="City")
    state: Optional[str] = Field(None, description="State")
    submarket_name: Optional[str] = Field(None, description="Submarket name")
    
    # Group 2: Financial Details (6 fields)
    sales_price: Optional[float] = Field(None, description="Sales price (decimal number)")
    annual_rent: Optional[float] = Field(None, description="Annual rent (decimal number)")
    lease_type: Optional[str] = Field(None, description="Lease type")
    increases: Optional[str] = Field(None, description="Rent increase description")
    numerical_rent_increase: Optional[float] = Field(None, description="Rent increase percentage (decimal number)")
    frequency_of_rent_increase: Optional[float] = Field(None, description="Years between rent increases (decimal number)")
    
    # Group 3: Physical Property (4 fields)
    year_built_renovated: Optional[float] = Field(None, description="Year built or renovated (decimal number)")
    building_sf: Optional[float] = Field(None, description="Building square footage (decimal number)")
    land_acres: Optional[float] = Field(None, description="Land in acres (decimal number)")
    landlord_expense_responsibilities: Optional[str] = Field(None, description="Landlord expense responsibilities")
    
    # Group 4: Lease Details (4 fields)
    sale_date: Optional[datetime] = Field(None, description="Sale date (ISO format)")
    lease_expiration_date: Optional[datetime] = Field(None, description="Lease expiration date (ISO format)")
    guarantor_operator: Optional[str] = Field(None, description="Guarantor (Operator)")
    rent_commencement_date: Optional[datetime] = Field(None, description="Rent commencement date (ISO format)")
    
    # Geocoding fields
    latitude: Optional[float] = Field(None, description="Property latitude")
    longitude: Optional[float] = Field(None, description="Property longitude")
    
    # Metadata
    extraction_date: datetime = Field(default_factory=datetime.now)
    source_file: str = Field(..., description="Source OM file name")
    confidence_score: Optional[float] = Field(None, description="Extraction confidence") 