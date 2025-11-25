# Faster Whisper Setup

## Installation

1.  **Create Virtual Environment**:
    ```bash
    python -m venv venv
    ```

2.  **Activate Virtual Environment**:
    - Windows: `.\venv\Scripts\activate`
    - Linux/Mac: `source venv/bin/activate`

3.  **Install Requirements**:
    ```bash
    pip install -r requirements.txt
    ```

## Usage

Run the verification script:
```bash
python main.py
```

## NVIDIA GPU Support (Optional)

If you want to use your NVIDIA GPU, you need to install the cuBLAS and cuDNN libraries.
Refer to the [ctranslate2 documentation](https://opennmt.net/CTranslate2/installation.html) for more details.
