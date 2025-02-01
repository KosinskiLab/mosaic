import tensorflow as tf
from itertools import count
import glob
import os
import json
import datetime
import tarfile
import tempfile


class SEModel:
    idgen = count(0)
    AVAILABLE_MODELS = []
    MODELS = dict()
    MODELS_LOADED = False
    DEFAULT_COLOURS = [
        (66 / 255, 214 / 255, 164 / 255),
        (255 / 255, 243 / 255, 0 / 255),
        (255 / 255, 104 / 255, 0 / 255),
        (255 / 255, 13 / 255, 0 / 255),
        (174 / 255, 0 / 255, 255 / 255),
        (21 / 255, 0 / 255, 255 / 255),
        (0 / 255, 136 / 255, 266 / 255),
        (0 / 255, 247 / 255, 255 / 255),
        (0 / 255, 255 / 255, 0 / 255),
    ]
    DEFAULT_MODEL_ENUM = 1

    def __init__(self):
        # if not SEModel.MODELS_LOADED:
        #     SEModel.load_models()

        uid_counter = next(SEModel.idgen)
        self.uid = (
            int(datetime.datetime.now().strftime("%Y%m%d%H%M%S%f") + "000")
            + uid_counter
        )
        self.title = "Unnamed model"
        self.colour = SEModel.DEFAULT_COLOURS[
            (uid_counter) % len(SEModel.DEFAULT_COLOURS)
        ]
        self.apix = -1.0
        self.compiled = False
        self.box_size = -1
        self.model = None
        self.model_enum = SEModel.DEFAULT_MODEL_ENUM
        self.epochs = 25
        self.batch_size = 32
        self.train_data_path = "(path to training dataset)"
        self.active = True
        self.export = True
        self.blend = False
        self.show = True
        self.alpha = 0.75
        self.threshold = 0.5
        self.overlap = 0.2
        self.active_tab = 0
        self.background_process_train = None
        self.background_process_apply = None
        self.n_parameters = 0
        self.n_copies = 4
        self.excess_negative = 30
        self.info = ""
        self.info_short = ""
        self.loss = 0.0
        self.data = None
        self.bcprms = dict()  # backward compatibility params dict.
        self.emit = False
        self.absorb = False
        self.interactions = list()  # list of ModelInteraction objects.

    def load(self, file_path, compile=False):
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                with tarfile.open(file_path, "r") as archive:
                    archive.extractall(path=temp_dir)

                model_file = glob.glob(os.path.join(temp_dir, "*_weights.h5"))[0]
                metadata_file = glob.glob(os.path.join(temp_dir, "*_metadata.json"))[0]

                self.model = tf.keras.models.load_model(model_file, compile=compile)

                with open(metadata_file, "r") as f:
                    metadata = json.load(f)

                self.title = metadata["title"]
                self.colour = metadata["colour"]
                self.apix = metadata["apix"]
                self.compiled = metadata["compiled"]
                self.box_size = metadata["box_size"]
                self.model_enum = metadata["model_enum"]
                self.epochs = metadata["epochs"]
                self.batch_size = metadata["batch_size"]
                self.active = metadata["active"]
                self.blend = metadata["blend"]
                self.show = metadata["show"]
                self.alpha = metadata["alpha"]
                self.threshold = metadata["threshold"]
                self.overlap = metadata["overlap"]
                self.active_tab = metadata["active_tab"]
                self.n_parameters = metadata["n_parameters"]
                self.n_copies = metadata["n_copies"]
                self.info = metadata["info"]
                self.info_short = metadata["info_short"]
                self.excess_negative = metadata["excess_negative"]
                self.emit = metadata["emit"]
                self.absorb = metadata["absorb"]
                self.loss = metadata["loss"]

        except Exception as e:
            print("Error loading model - see details below", e)


def _segmentation_thread(model_path, data_paths, output_dir, gpu_id, overwrite=False):
    from keras.models import clone_model
    from keras.layers import Input

    if isinstance(gpu_id, int):
        os.environ["CUDA_VISIBLE_DEVICES"] = str(gpu_id)
    else:
        os.environ["CUDA_VISIBLE_DEVICES"] = gpu_id

    se_model = SEModel()
    se_model.load(model_path, compile=False)
    model = se_model.model
    new_input = Input(shape=(None, None, 1))
    new_model = clone_model(model, input_tensors=new_input)
    new_model.set_weights(model.get_weights())

    for j, p in enumerate(data_paths):
        tomo_name = os.path.basename(os.path.splitext(p)[0])
        out_path = os.path.join(output_dir, tomo_name + "__" + se_model.title + ".mrc")
        print(f"{j+1}/{len(data_paths)}({gpu_id}) - {p}")
        if os.path.exists(out_path) and not overwrite:
            continue

        in_voxel_size = mrcfile.open(p, header_only=True).voxel_size
        segmented_volume = _segment_tomo(p, new_model)
        segmented_volume = (segmented_volume * 255).astype(np.uint8)
        with mrcfile.new(out_path, overwrite=True) as mrc:
            mrc.set_data(segmented_volume)
            mrc.voxel_size = in_voxel_size


def _segment_tomo(tomo_path, model):
    volume = np.array(mrcfile.read(tomo_path).data)
    volume -= np.mean(volume)
    volume /= np.std(volume)
    segmented_volume = np.zeros_like(volume)

    for j in range(volume.shape[0]):
        segmented_volume[j, :, :] = np.squeeze(
            model.predict(volume[j, :, :][np.newaxis, :, :])
        )

    return segmented_volume
