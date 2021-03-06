#!/usr/bin/env python3
from vosk import Model, KaldiRecognizer, SetLogLevel
import wave
import json
import time
import os
import argparse
import configparser
import logging
import shutil
import stat


class Daemon:
    SLEEP = None
    WAV_RATE = None
    PY_PATH = None
    DATA_PATH = None
    OUTPUT_FILE_PATH = None
    INPUT_FILE_PATH = None
    TMP_FILE_PATH = None

    def __init__(self):
        Daemon.get_config()
        self.voice_model_init()
        self.recognizer_init()
        self.dir_init()
        logging.basicConfig(filename=self.lang + '_daemon.log',
                            level=logging.INFO,
                            format='%(asctime)s - %(levelname)s - %(message)s')
        logging.info("The daemon has been successfully launched!")
        logging.info("Daemon language: " + self.lang)

    @classmethod
    def get_config(cls):
        config = configparser.ConfigParser()
        config.read("config.ini")
        config_daemon = config['DAEMON']

        cls.WAV_RATE = int(config_daemon['WAV_RATE'])
        cls.SLEEP = float(config_daemon['DAEMON_RESPONSE_FREQUENCY'])
        cls.PY_PATH = config_daemon['PY_PATH']
        cls.DATA_PATH = config_daemon['DATA_PATH']
        cls.INPUT_FILE_PATH = Daemon.DATA_PATH + config_daemon['INPUT_FILE_PATH']
        cls.OUTPUT_FILE_PATH = Daemon.DATA_PATH + config_daemon['OUTPUT_FILE_PATH']
        cls.TMP_FILE_PATH = Daemon.DATA_PATH + config_daemon['TMP_FILE_PATH']

    def voice_model_init(self):
        parser = argparse.ArgumentParser(description="voice recognition daemon")
        parser.add_argument("lang", type=str, help='Language for recognizer', default="ru", nargs='?', const="ru")
        args = parser.parse_args()
        self.lang = args.lang
        model_path = Daemon.PY_PATH + "models/" + self.lang
        self.voice_model = Model(model_path)

    def recognizer_init(self):
        self.default_rec = KaldiRecognizer(self.voice_model, Daemon.WAV_RATE)

    @staticmethod
    def dir_init():
        os.makedirs(Daemon.INPUT_FILE_PATH, exist_ok=True)
        os.makedirs(Daemon.OUTPUT_FILE_PATH, exist_ok=True)
        os.makedirs(Daemon.TMP_FILE_PATH, exist_ok=True)

        stat_mode = stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR | \
                    stat.S_IRGRP | stat.S_IWGRP | stat.S_IXGRP | \
                    stat.S_IROTH | stat.S_IWOTH | stat.S_IXOTH
        os.chmod(path=Daemon.INPUT_FILE_PATH, mode=stat_mode)
        os.chmod(path=Daemon.OUTPUT_FILE_PATH, mode=stat_mode)
        os.chmod(path=Daemon.TMP_FILE_PATH, mode=stat_mode)

    def start(self):
        filenames = self.get_new_files()
        if filenames:
            print("Filenames: ", filenames)
        for filename in filenames:
            if self.is_supported_lang(filename):
                print('Work on: ', filename)
                self.recognize(filename)

    def is_supported_lang(self, filename):
        filename_codec = os.path.splitext(filename)[1]
        result = filename.startswith(self.lang) and filename_codec not in ['.dict']
        return result

    def recognize(self, filename):
        start_time = time.time()
        self.rec = self.make_recognizer(filename)
        wav_file = self.fileToWav(filename)
        text = self.wav_to_text(wav_file)
        self.write_transcript(filename, text)
        self.delete_recognized_wav(wav_file)
        time_for_recognizer = time.time() - start_time
        logging.info(f"File: {wav_file}; "
                     f"recognized text: {text}; "
                     f"time for recognize {'%.3f' % time_for_recognizer} second")

    def make_recognizer(self, filename):
        dict = self.get_dict(filename)
        if dict:
            rec = KaldiRecognizer(self.voice_model, Daemon.WAV_RATE, dict)
        else:
            rec = self.default_rec
        return rec

    @staticmethod
    def get_dict(filename):
        input_dict = os.path.splitext(Daemon.INPUT_FILE_PATH + filename)[0] + ".dict"
        dict = []
        if os.path.exists(input_dict):
            with open(input_dict, "r") as filename_dict:
                dict = filename_dict.read()
            os.remove(input_dict)
        return dict

    @staticmethod
    def fileToWav(filename):
        input_file = Daemon.INPUT_FILE_PATH + filename
        wav_file = Daemon.TMP_FILE_PATH + os.path.splitext(filename)[0] + ".wav"
        # using ffmpeg app for convert all audio file for .wav with rate=16000 and mono
        ffmpeg_command = "ffmpeg -hide_banner -loglevel error -i {input_file} -y -ac 1 -ar {sample_rate} {output_file}" \
            .format(input_file=input_file,
                    sample_rate=Daemon.WAV_RATE,
                    output_file=wav_file)
        os.system(ffmpeg_command)
        os.remove(input_file)
        return wav_file

    @staticmethod
    def get_new_files():
        files = os.listdir(Daemon.INPUT_FILE_PATH)
        return files

    def wav_to_text(self, filename):
        with open(filename, "rb") as wf:
            wf.read(44)  # skip wav header
            recognized_words = []

            while True:
                data = wf.read(4000)
                if len(data) == 0:
                    break
                if self.rec.AcceptWaveform(data):
                    res = json.loads(self.rec.Result())
                    recognized_words.append(res['text'])

            res = json.loads(self.rec.FinalResult())
            recognized_words.append(res['text'])
            text = ' '.join(recognized_words)
        return text

    @staticmethod
    def write_transcript(filename, text):
        transctipt_path = Daemon.OUTPUT_FILE_PATH + os.path.splitext(filename)[0] + '.txt'
        with open(transctipt_path, 'w') as transcript:
            transcript.write(text)

    @staticmethod
    def delete_recognized_wav(filename):
        wav_file = filename
        if os.path.exists(wav_file):
            os.remove(wav_file)


if __name__ == '__main__':
    start_time = time.time()
    SetLogLevel(-1)
    daemon = Daemon()
    time_to_init = time.time() - start_time
    logging.info(f"Initialized in {'%.3f' % time_to_init} seconds")
    try:
        while True:
            daemon.start()
            time.sleep(Daemon.SLEEP)

    except FileNotFoundError:
        logging.error(FileNotFoundError, exc_info=True)

    except wave.Error:
        logging.error(wave.Error, exc_info=True)

    except Exception as e:
        logging.error(e, exc_info=True)

    finally:
        logging.exception("Daemon was interrupted!")
        shutil.rmtree(Daemon.DATA_PATH + Daemon.INPUT_FILE_PATH)
        shutil.rmtree(Daemon.DATA_PATH + Daemon.OUTPUT_FILE_PATH)
        shutil.rmtree(Daemon.DATA_PATH + Daemon.TMP_FILE_PATH)
        raise
