import tkinter as tk
from tkinter import messagebox
from tkinter import filedialog
import cv2
from PIL import Image, ImageTk
import requests
from requests.auth import HTTPBasicAuth
import threading
import time
import numpy as np
import subprocess
import queue
import os

# ============================================================
# Camera settings
# ============================================================

CAMERA_IP = "192.168.20.26"
USERNAME = "admin"
PASSWORD = "ZEISS1846"

STREAM_URL = f"http://{CAMERA_IP}:8080/?action=stream"
SNAPSHOT_URL = f"http://{CAMERA_IP}:8080/?action=snapshot"

FRAME_WIDTH = 960
FRAME_HEIGHT = 540
FRAME_SIZE = FRAME_WIDTH * FRAME_HEIGHT * 3


# ============================================================
# GUI settings
# ============================================================

PREVIEW_WIDTH = 640
PREVIEW_HEIGHT = 360

# How often the GUI updates the displayed image
# 0.10 seconds = approximately 10 FPS
GUI_UPDATE_INTERVAL = 100


class StemiApp:

    def __init__(self, root):

        self.root = root

        self.root.title("Stemi Cell Counter")
        self.root.geometry("1100x700")

        # ----------------------------------------------------
        # State
        # ----------------------------------------------------

        self.running = True

        # Most recent camera frame
        self.current_frame = None

        # Lock protects current_frame between threads
        self.frame_lock = threading.Lock()

        # ----------------------------------------------------
        # Layout
        # ----------------------------------------------------

        self.video_label = tk.Label(
            root,
            width=PREVIEW_WIDTH,
            height=PREVIEW_HEIGHT,
            bg="black"
        )

        self.video_label.pack(
            side="left",
            padx=20,
            pady=20
        )

        self.button_frame = tk.Frame(root)

        self.button_frame.pack(
            side="right",
            padx=40
        )

        self.count_button = tk.Button(
            self.button_frame,
            text="COUNT CELLS",
            font=("Arial", 24, "bold"),
            width=12,
            height=3,
            command=self.count_cells
        )

        self.count_button.pack()

        self.capture_button = tk.Button(
            self.button_frame,
            text="Capture",
            font=("Arial", 24, "bold"),
            width=12,
            height=3,
            command=self.capture_Frame
        )

        self.capture_button.pack()

        # ----------------------------------------------------
        # Start camera thread
        # ----------------------------------------------------

        self.camera_thread = threading.Thread(
            target=self.camera_loop,
            daemon=True
        )

        self.camera_thread.start()

        # ----------------------------------------------------
        # Start GUI update loop
        # ----------------------------------------------------

        self.update_video()

        # ----------------------------------------------------
        # Window close event
        # ----------------------------------------------------

        self.root.protocol(
            "WM_DELETE_WINDOW",
            self.close
        )

    # ========================================================
    # Camera acquisition
    # ========================================================

    def camera_loop(self):

        print("Starting camera stream...")

        try:
            response = requests.get(
                STREAM_URL,
                auth=HTTPBasicAuth(USERNAME, PASSWORD),
                stream=True,
                timeout=(5, None)
            )

            response.raise_for_status()

            print("Camera connected")
            print("Content-Type:", response.headers.get("Content-Type"))

        except Exception as e:

            print("Could not connect to camera:")
            print(e)

            return


        # -------------------------------------------------
        # Start FFmpeg
        # -------------------------------------------------

        ffmpeg_cmd = [

            r"C:\Users\CVUser\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-9.0.1-full_build\bin\ffmpeg.exe",

            "-loglevel", "error",

            "-fflags", "nobuffer",
            "-flags", "low_delay",
            "-f", "h264",
            "-i", "pipe:0",

            "-vf", "scale=960:540",

            "-f", "rawvideo",
            "-pix_fmt", "bgr24",

            "pipe:1"
        ]


        ffmpeg = subprocess.Popen(
            ffmpeg_cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=None,
            bufsize=10**8
        )

        print("FFmpeg started")


        # -------------------------------------------------
        # Thread: read decoded frames from FFmpeg
        # -------------------------------------------------

        def read_frames():

            print("Frame reader started")

            while self.running:

                try:

                    raw_frame = b""

                    while len(raw_frame) < FRAME_SIZE:
                        chunk = ffmpeg.stdout.read(FRAME_SIZE - len(raw_frame))
                        if not chunk:
                            break
                        raw_frame += chunk

                    if len(raw_frame) != FRAME_SIZE:
                        print("FFmpeg ended with incomplete frame:", len(raw_frame), "/", FRAME_SIZE)
                        break

                    frame = np.frombuffer(
                        raw_frame,
                        dtype=np.uint8
                    )

                    frame = frame.reshape(
                        (
                            FRAME_HEIGHT,
                            FRAME_WIDTH,
                            3
                        )
                    )


                    # Always keep only newest frame
                    with self.frame_lock:
                        self.current_frame = frame.copy()


                except Exception as e:

                    if self.running:
                        print(
                            "Frame reader error:",
                            e
                        )

                    break


        frame_thread = threading.Thread(

            target=read_frames,

            daemon=True
        )

        frame_thread.start()


        # -------------------------------------------------
        # Read multipart stream and feed H264 to FFmpeg
        # -------------------------------------------------

        buffer = b""


        try:

            for chunk in response.iter_content(
                chunk_size=8192
            ):

                if not self.running:
                    break


                if not chunk:
                    continue


                buffer += chunk


                while True:


                    # Find multipart boundary
                    header_end = buffer.find(
                        b"\r\n\r\n"
                    )


                    if header_end == -1:
                        break


                    header = buffer[
                        :header_end
                    ]


                    # Find Content-Length
                    content_length = None


                    for line in header.split(
                        b"\r\n"
                    ):

                        if line.lower().startswith(
                            b"content-length:"
                        ):

                            try:

                                content_length = int(
                                    line.split(
                                        b":"
                                    )[1].strip()
                                )

                            except Exception:

                                content_length = None


                    if content_length is None:

                        # Remove bad data and continue
                        buffer = buffer[
                            header_end + 4:
                        ]

                        continue


                    data_start = header_end + 4

                    data_end = (
                        data_start +
                        content_length
                    )


                    # Not enough data yet
                    if len(buffer) < data_end:

                        break


                    # Extract H264 packet
                    h264_data = buffer[
                        data_start:data_end
                    ]


                    # Remove processed packet
                    buffer = buffer[
                        data_end:
                    ]


                    # Feed packet to FFmpeg
                    try:
                        ffmpeg.stdin.write(h264_data)
                        ffmpeg.stdin.flush()

                    except BrokenPipeError:
                        print("FFmpeg pipe close")
                        self.running = False
                        break


        except Exception as e:

            if self.running:

                print(
                    "Camera stream error:",
                    e
                )


        finally:

            print(
                "Stopping camera stream"
            )


            try:

                response.close()

            except Exception:

                pass


            try:

                ffmpeg.stdin.close()

            except Exception:

                pass


            try:

                ffmpeg.terminate()

            except Exception:

                pass


    # ========================================================
    # GUI video update
    # ========================================================

    def update_video(self):

        if not self.running:
            return

        frame = None

        # Get the newest frame
        with self.frame_lock:

            if self.current_frame is not None:

                frame = self.current_frame.copy()

        if frame is not None:

            # ------------------------------------------------
            # Resize BEFORE converting to PIL
            # ------------------------------------------------

            frame = cv2.resize(
                frame,
                (PREVIEW_WIDTH, PREVIEW_HEIGHT),
                interpolation=cv2.INTER_AREA
            )

            # OpenCV BGR -> RGB
            frame_rgb = cv2.cvtColor(
                frame,
                cv2.COLOR_BGR2RGB
            )

            # Convert to PIL
            image = Image.fromarray(frame_rgb)

            # Convert to Tkinter image
            photo = ImageTk.PhotoImage(image)

            # Display
            self.video_label.configure(
                image=photo
            )

            # Keep reference
            self.video_label.image = photo

        # Schedule next GUI update
        self.root.after(
            GUI_UPDATE_INTERVAL,
            self.update_video
        )


    def capture_Frame(self):
        filepath = filedialog.asksaveasfilename(title="Save Image", defaultextension=".jpg",
                                                 filetypes=[("JPEG image", "*.jpg"), ("All files", "*.*")],
                                                 initialfile=time.strftime("capture_%Y%m%d_%H%M%S.jpg"))
        if not filepath:
            return
        
        self.capture_button.config(text="Capturing...", state="disabled")

        threading.Thread(target=self.capture_image, args=(filepath,), daemon=True).start()

    def capture_image(self, filepath):
        try:
            print("Taking snapshot")

            response = requests.get(
                SNAPSHOT_URL,
                auth=HTTPBasicAuth(USERNAME, PASSWORD),
                timeout=10
            )

            response.raise_for_status()

            image_data = response.content

            print(f"Snapshot received:" f"{len(image_data)} bytes")

            with open(filepath, "wb") as f:
                f.write(image_data)
            
            print("Image saved: ", filepath)

            def capture_finished():
                self.capture_button.config(
                    text="Capture Image", state="normal"
                )

                messagebox.showinfo(
                    "Capture Complete",
                    f"Image saved to:\n{filepath}"
                )

            self.root.after(0,
                            capture_finished
                            )
        
        except Exception as e:
            print("Capture error:", e)

            self.root.after(0,
                            lambda: self.capture_button.config(text="Capture Image", state="normal")
                            )
            self.root.after(0,
                            self.show_error,
                            str(e)
                            )

    # ========================================================
    # Count cells
    # ========================================================

    def count_cells(self):

        self.count_button.config(
            text="COUNTING...",
            state="disabled"
        )

        thread = threading.Thread(
            target=self.run_counting,
            daemon=True
        )

        thread.start()


    # ========================================================
    # Cell counting
    # ========================================================

    def run_counting(self):

        try:

            print("Taking high-resolution snapshot...")

            # ------------------------------------------------
            # Get high-resolution snapshot
            # ------------------------------------------------

            response = requests.get(
                SNAPSHOT_URL,
                auth=HTTPBasicAuth(
                    USERNAME,
                    PASSWORD
                ),
                timeout=10
            )

            response.raise_for_status()

            image_data = response.content

            # ------------------------------------------------
            # Decode JPEG
            # ------------------------------------------------

            image_array = cv2.imdecode(
                np.frombuffer(
                    image_data,
                    dtype=np.uint8
                ),
                cv2.IMREAD_COLOR
            )

            if image_array is None:

                raise RuntimeError(
                    "Could not decode camera image."
                )

            print(
                f"Snapshot received: "
                f"{image_array.shape[1]} x "
                f"{image_array.shape[0]}"
            )

            # ------------------------------------------------
            # YOUR CELL COUNTING ALGORITHM
            # ------------------------------------------------

            # Replace this with your actual algorithm.
            #
            # Example:
            #
            # count = count_cells(image_array)

            count = "TEST"

            # ------------------------------------------------
            # Show result
            # ------------------------------------------------

            self.root.after(
                0,
                self.show_result,
                count
            )

        except Exception as e:

            self.root.after(
                0,
                self.show_error,
                str(e)
            )


    # ========================================================
    # Display result
    # ========================================================

    def show_result(self, result):

        self.count_button.config(
            text=f"CELLS: {result}",
            state="normal"
        )


    # ========================================================
    # Display error
    # ========================================================

    def show_error(self, error):

        messagebox.showerror(
            "Error",
            error
        )

        self.count_button.config(
            text="COUNT CELLS",
            state="normal"
        )


    # ========================================================
    # Close application
    # ========================================================

    def close(self):
        print("Closeing application...")
        self.running = False
        self.root.destroy()


# ============================================================
# Start application
# ============================================================

root = tk.Tk()

app = StemiApp(root)

root.mainloop()