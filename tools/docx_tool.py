# Creating Word files (python-docx)
from docx import Document
from typing import List, Optional
from docx.shared import Inches
from pydantic import BaseModel, Field
from langchain_core.tools import tool
import os


class CreateDocxInput(BaseModel):
    title: str = Field(..., description="Title of the document")
    paragraphs: List[str] = Field(..., description="List of paragraph texts")
    table_data: Optional[List[List[str]]] = Field(
        None, description="Table rows (first row is header)")
    image_path: Optional[str] = Field(None, description="Path to an image")
    save_path: str = Field(..., description="Output path for the .docx file")


@tool(
    args_schema=CreateDocxInput,
    description="""
Create a .docx file with: title (str), paragraphs (list[str]), optional table_data (list[list[str]]), image_path (str or ""), and save_path (str).
Use this tool ONLY when the user explicitly asks to generate a Word document (e.g., 'generate a Word file', 'create DOCX', 'make a Word report', etc.).
In all other cases, do not use this tool.
In your response, output JSON ONLY without any comments or explanations.
"""
)
def create_docx(title: str, paragraphs: List[str],
                table_data: Optional[List[List[str]]] = None,
                image_path: Optional[str] = "",
                save_path: str = "generated_docs/output.docx") -> str:
    document = Document()
    if title:
        document.add_heading(title, level=0)

    if paragraphs:
        for para in paragraphs:
            document.add_paragraph(para)

    if table_data:
        rows = len(table_data)
        cols = len(table_data[0])
        table = document.add_table(rows=rows, cols=cols)
        for i, row in enumerate(table_data):
            for j, cell in enumerate(row):
                table.cell(i, j).text = str(cell)

    if image_path and os.path.exists(image_path):
        document.add_picture(image_path, width=Inches(4))

    document.save(save_path)
    print("Saving to:", save_path)
    return f'Document saved as "{save_path}"'
