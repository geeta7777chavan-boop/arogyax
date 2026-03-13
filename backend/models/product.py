from pydantic import BaseModel
from typing import Optional


class ProductOut(BaseModel):
    id:                   int
    pzn:                  int
    name:                 str
    price:                float
    package_size:         Optional[str]
    description:          Optional[str]
    stock_quantity:       int
    prescription_required: bool


class StockUpdateIn(BaseModel):
    stock_quantity: int