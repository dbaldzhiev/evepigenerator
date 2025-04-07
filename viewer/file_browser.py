from tkinter import filedialog, Tk

def select_json_file():
    root = Tk()
    root.withdraw()
    file_path = filedialog.askopenfilename(filetypes=[("JSON files", "*.json")])
    return file_path
