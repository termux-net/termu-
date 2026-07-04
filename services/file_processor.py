import base64
from fastapi import UploadFile

class FileProcessor:
    @staticmethod
    async def process_file(file: UploadFile) -> dict:
        content = await file.read()
        file_type = file.content_type
        
        if file_type.startswith('image/'):
            return {
                "type": "image",
                "data": base64.b64encode(content).decode('utf-8'),
                "mime_type": file_type,
                "filename": file.filename
            }
        elif file_type == 'application/pdf':
            return {
                "type": "pdf",
                "data": base64.b64encode(content).decode('utf-8'),
                "filename": file.filename
            }
        else:
            text_content = content.decode('utf-8', errors='ignore')
            return {
                "type": "text",
                "content": text_content[:5000],
                "filename": file.filename
            }
