"""
Paper: "Fast and Accurate Image Super Resolution by Deep CNN with Skip Connection and Network in Network"
Ver: 2

functions for loading/converting data
"""

import configparser
import logging
import os
import random

import numpy as np
from scipy import misc

from helper import utilty as util
import cv2

INPUT_IMAGE_DIR = "input"
INTERPOLATED_IMAGE_DIR = "interpolated"
TRUE_IMAGE_DIR = "true"


def build_image_set(file_path, channels=1, scale=1, convert_ycbcr=True, resampling_method="bicubic",
                    print_console=True):
    true_image = util.set_image_alignment(util.load_image(file_path, print_console=print_console), scale)

    if channels == 1 and true_image.shape[2] == 3 and convert_ycbcr:
        true_image = util.convert_rgb_to_y(true_image)

    # Avoid creating input, bicubic images, as they can be created from true image while training
    #input_image = util.resize_image_by_pil(true_image, 1.0 / scale, resampling_method=resampling_method)
    #input_interpolated_image = util.resize_image_by_pil(input_image, scale, resampling_method=resampling_method)

    #return input_image, input_interpolated_image, true_image
    return true_image, true_image, true_image


def load_input_image(filename, width=0, height=0, channels=1, scale=1, alignment=0, convert_ycbcr=True,
                     print_console=True):
    image = util.load_image(filename, print_console=print_console)
    return build_input_image(image, width, height, channels, scale, alignment, convert_ycbcr)


def build_input_image(image, width=0, height=0, channels=1, scale=1, alignment=0, convert_ycbcr=True):
    """
    build input image from file.
    crop, adjust the image alignment for the scale factor, resize, convert color space.
    """

    if width != 0 and height != 0:
        if image.shape[0] != height or image.shape[1] != width:
            x = (image.shape[1] - width) // 2
            y = (image.shape[0] - height) // 2
            image = image[y: y + height, x: x + width, :]

    if alignment > 1:
        image = util.set_image_alignment(image, alignment)

    if channels == 1 and image.shape[2] == 3:
        if convert_ycbcr:
            image = util.convert_rgb_to_y(image)
    else:
        if convert_ycbcr:
            image = util.convert_rgb_to_ycbcr(image)

    if scale != 1:
        image = util.resize_image_by_pil(image, 1.0 / scale)

    return image


class BatchDataSets:
    def __init__(self, scale, batch_dir, batch_image_size, stride_size=0, channels=1, resampling_method="bicubic", patches_cnt=0, compress_input_q=0):

        self.scale = scale
        self.batch_image_size = batch_image_size
        if stride_size == 0:
            self.stride = batch_image_size // 2
        else:
            self.stride = stride_size
        self.channels = channels
        self.resampling_method = resampling_method
        self.count = 0
        self.batch_dir = batch_dir
        self.batch_index = None
        self.patches_cnt = patches_cnt
        if self.patches_cnt == 0:
            if self.scale <= 2:
                self.patches_cnt = 150000
            else:
                self.patches_cnt = 60000
        self.compress_input_q = compress_input_q

    def build_batch(self, data_dir):
        """ Build batch images and. """

        print("Building batch images for %s..." % self.batch_dir)
        filenames = util.get_files_in_directory(data_dir)
        images_count = 0

        #util.make_dir(self.batch_dir)
        #util.clean_dir(self.batch_dir)
        #util.make_dir(self.batch_dir + "/" + INPUT_IMAGE_DIR)
        #util.make_dir(self.batch_dir + "/" + INTERPOLATED_IMAGE_DIR)
        #util.make_dir(self.batch_dir + "/" + TRUE_IMAGE_DIR)

        patches_cnt = self.patches_cnt
        
        # allocate memory for patches
        hr_patch_dim = self.batch_image_size * self.scale
        pmem1 = hr_patch_dim * hr_patch_dim
        patches_mem1 = patches_cnt * pmem1        
        self.true_images = np.zeros(
            shape=[patches_cnt+1500, self.batch_image_size * self.scale, self.batch_image_size * self.scale, 1],
            dtype=np.uint8)
        logging.info("Allocated HR ({}x{}) patches_cnt: {}, patches_mem1: {}".format(hr_patch_dim, hr_patch_dim, patches_cnt, patches_mem1))                    
        
        # allocate memory for compressed low-resolution patches
        if self.compress_input_q > 1:
            pmem2 = self.batch_image_size * self.batch_image_size
            patches_mem2 = patches_cnt * pmem2
            self.compress_images_lr = np.zeros(
                shape=[patches_cnt+1500, self.batch_image_size, self.batch_image_size, 1],
                dtype=np.uint8)                   
            logging.info("Allocated compressed (y) patches_cnt: {}, patches_mem2: {}".format(patches_cnt, patches_mem2))    
            
        processed_images = 0
        for filename in filenames:
            output_window_size = self.batch_image_size * self.scale
            output_window_stride = self.stride * self.scale

            if self.compress_input_q > 1:  
                # read RGB HR image
                input_image_rgb, input_interpolated_image_rgb, true_image_rgb = \
                    build_image_set(filename, channels=3, resampling_method=self.resampling_method,
                                    scale=self.scale, print_console=False)  
                                    
                # split each RGB channel and batch
                batch_HR_r = util.get_split_images(true_image_rgb[:,:,0:1].astype(np.uint8), output_window_size, stride=output_window_stride)                
                batch_HR_g = util.get_split_images(true_image_rgb[:,:,1:2].astype(np.uint8), output_window_size, stride=output_window_stride)                
                batch_HR_b = util.get_split_images(true_image_rgb[:,:,2:3].astype(np.uint8), output_window_size, stride=output_window_stride)                
                if batch_HR_r is None:
                    # if the original image size * scale is less than batch image size
                    continue
                    
                # concat each r,g,b batch images
                batch_HR_rgb = np.zeros(shape=[batch_HR_r.shape[0], batch_HR_r.shape[1], batch_HR_r.shape[2], 3], dtype=np.uint8)
                batch_HR_rgb[:,:,:,0:1] = batch_HR_r
                batch_HR_rgb[:,:,:,1:2] = batch_HR_g
                batch_HR_rgb[:,:,:,2:3] = batch_HR_b   

                # Each patch: downscale->compress->convert_to_y
                input_count = batch_HR_rgb.shape[0]
                for i in range(input_count):
                    # create LR RGB image
                    image_lr_rgb = util.resize_image_by_pil(batch_HR_rgb[i], 1.0 / self.scale, resampling_method=self.resampling_method)
                                        
                    # compress LR RGB image: encode and decode
                    encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), self.compress_input_q]
                    ret, enc_img = cv2.imencode('.jpg', image_lr_rgb, encode_param)
                    dec_img = cv2.imdecode(enc_img, 1) 
                    
                    # convert y
                    image_lr_y = util.convert_rgb_to_y(dec_img)
                    image_hr_y = util.convert_rgb_to_y(batch_HR_rgb[i])
                    
                    # save compressed LR y images
                    self.compress_images_lr[images_count] = image_lr_y    
                    # save uncompressed HR y image
                    self.true_images[images_count] = image_hr_y                                    
                    images_count += 1
            else:
                # Read RGB HR and convert to YUV HR
                input_image, input_interpolated_image, true_image = \
                    build_image_set(filename, channels=self.channels, resampling_method=self.resampling_method,
                                    scale=self.scale, print_console=False)   

                # split Y_HR images
                true_batch_images = util.get_split_images(true_image, output_window_size, stride=output_window_stride)
                if true_batch_images is None:
                    # if the original image size * scale is less than batch image size
                    continue
                input_count = true_batch_images.shape[0]

                for i in range(input_count):
                    self.true_images[images_count] = true_batch_images[i]                                    
                    images_count += 1

            if (images_count * pmem1) > (patches_mem1 - 100000):
                logging.info(" ### Stopping patch process: Increase patches memory to process remaining patches also")                
                break
                
            processed_images += 1
            if processed_images % 10 == 0:
                print('.', end='', flush=True)

        logging.info("Finished batch creation.")
        logging.info(" --- processed images: ".format(processed_images))        
        self.count = images_count

        logging.info("%d mini-batch images are built(saved).\n" % images_count)

        #config = configparser.ConfigParser()
        #config.add_section("batch")
        #config.set("batch", "count", str(images_count))
        #config.set("batch", "scale", str(self.scale))
        #config.set("batch", "batch_image_size", str(self.batch_image_size))
        #config.set("batch", "stride", str(self.stride))
        #config.set("batch", "channels", str(self.channels))
        #
        #with open(self.batch_dir + "/batch_images.ini", "w") as configfile:
        #    config.write(configfile)

    def load_batch_counts(self):
        """ load already built batch images. """

        if not os.path.isdir(self.batch_dir):
            self.count = 0
            return

        config = configparser.ConfigParser()
        try:
            with open(self.batch_dir + "/batch_images.ini") as f:
                config.read_file(f)
            self.count = config.getint("batch", "count")

        except IOError:
            self.count = 0
            return

    #def load_all_batch_images(self):
    #
    #    print("Allocating memory for all batch images...")
    #    # Avoided creating input, bicubic images, as they can be created from true image while training 
    #    #self.input_images = np.zeros(shape=[self.count, self.batch_image_size, self.batch_image_size, 1],
    #    #                             dtype=np.uint8)  # type: np.ndarray
    #    #self.input_interpolated_images = np.zeros(
    #    #    shape=[self.count, self.batch_image_size * self.scale, self.batch_image_size * self.scale, 1],
    #    #    dtype=np.uint8)  # type: np.ndarray
    #    self.true_images = np.zeros(
    #        shape=[self.count, self.batch_image_size * self.scale, self.batch_image_size * self.scale, 1],
    #        dtype=np.uint8)  # type: np.ndarray
    #
    #    print("Loading all batch images...")
    #    for i in range(self.count):
    #        #self.input_images[i] = self.load_input_batch_image(i)
    #        #self.input_interpolated_images[i] = self.load_interpolated_batch_image(i)
    #        self.true_images[i] = self.load_true_batch_image(i)
    #        if i % 1000 == 0:
    #            print('.', end='', flush=True)
    #    print("Load finished.")

    def release_batch_images(self):

        if hasattr(self, 'input_images'):
            del self.input_images
        self.input_images = None

        if hasattr(self, 'input_interpolated_images'):
            del self.input_interpolated_images
        self.input_interpolated_images = None

        if hasattr(self, 'true_images'):
            del self.true_images
            if self.compress_input_q > 1:
                del self.compress_images_lr
        self.true_images = None
        if self.compress_input_q > 1:
            self.compress_images_lr = None

    # verify already created batch has same properties as batch requested in current training instance
    def is_batch_exist(self):
        if not os.path.isdir(self.batch_dir):
            return False

        config = configparser.ConfigParser()
        try:
            with open(self.batch_dir + "/batch_images.ini") as f:
                config.read_file(f)

            if config.getint("batch", "count") <= 0:
                return False

            if config.getint("batch", "scale") != self.scale:
                return False
            # Avoid checking batch size, to allow variable batch sizes
            #if config.getint("batch", "batch_image_size") != self.batch_image_size:
            #    return False
            # Avoid checking stride size
            if config.getint("batch", "stride") != self.stride:
                return False
            if config.getint("batch", "channels") != self.channels:
                return False

            return True

        except IOError:
            return False

    def init_batch_index(self):
        self.batch_index = random.sample(range(0, self.count), self.count)
        self.index = 0

    def get_next_image_no(self):

        if self.index >= self.count:
            self.init_batch_index()

        image_no = self.batch_index[self.index]
        self.index += 1
        return image_no

    def load_batch_image_from_disk(self, image_number):

        image_number = image_number % self.count

        input_image = self.load_input_batch_image(image_number)
        input_interpolated = self.load_interpolated_batch_image(image_number)
        true = self.load_true_batch_image(image_number)

        return input_image, input_interpolated, true

    def load_batch_image(self, max_value):

        number = self.get_next_image_no()
        if max_value == 255:
            # label (HR) image
            true_image = self.true_images[number]
            
            # create input images (LR) from true image
            if self.compress_input_q > 1:
                input_image = self.compress_images_lr[number]
            else:
                input_image = util.resize_image_by_pil(true_image, 1.0 / self.scale, resampling_method=self.resampling_method)
                
            # interpolate input for skip connection
            input_interpolated_image = util.resize_image_by_pil(input_image, self.scale, resampling_method=self.resampling_method)        
            return input_image, input_interpolated_image, true_image
        else:
            scale = max_value / 255.0
            return np.multiply(self.input_images[number], scale), \
                np.multiply(self.input_interpolated_images[number], scale), \
                np.multiply(self.true_images[number], scale)

    def load_input_batch_image(self, image_number):
        image = misc.imread(self.batch_dir + "/" + INPUT_IMAGE_DIR + "/%06d.bmp" % image_number)
        return image.reshape(image.shape[0], image.shape[1], 1)

    def load_interpolated_batch_image(self, image_number):
        image = misc.imread(self.batch_dir + "/" + INTERPOLATED_IMAGE_DIR + "/%06d.bmp" % image_number)
        return image.reshape(image.shape[0], image.shape[1], 1)

    def load_true_batch_image(self, image_number):
        image = misc.imread(self.batch_dir + "/" + TRUE_IMAGE_DIR + "/%06d.bmp" % image_number)
        return image.reshape(image.shape[0], image.shape[1], 1)

    def save_input_batch_image(self, image_number, image):
        return util.save_image(self.batch_dir + "/" + INPUT_IMAGE_DIR + "/%06d.bmp" % image_number, image)

    def save_interpolated_batch_image(self, image_number, image):
        return util.save_image(self.batch_dir + "/" + INTERPOLATED_IMAGE_DIR + "/%06d.bmp" % image_number, image)

    def save_true_batch_image(self, image_number, image):
        return util.save_image(self.batch_dir + "/" + TRUE_IMAGE_DIR + "/%06d.bmp" % image_number, image)


class DynamicDataSets:
    def __init__(self, scale, batch_image_size, channels=1, resampling_method="bicubic"):

        self.scale = scale
        self.batch_image_size = batch_image_size
        self.channels = channels
        self.resampling_method = resampling_method

        self.filenames = []
        self.count = 0
        self.batch_index = None
       
    def set_data_dir(self, data_dir):
        self.filenames = util.get_files_in_directory(data_dir)
        self.count = len(self.filenames)
        if self.count <= 0:
            logging.error("Data Directory is empty.")
            exit(-1)

    def init_batch_index(self):
        self.batch_index = random.sample(range(0, self.count), self.count)
        self.index = 0

    def get_next_image_no(self):

        if self.index >= self.count:
            self.init_batch_index()

        image_no = self.batch_index[self.index]
        self.index += 1
        return image_no

    def load_batch_image(self, max_value):

        """ index won't be used. """

        image = None
        while image is None:
            image = self.load_random_patch(self.filenames[self.get_next_image_no()])

        if random.randrange(2) == 0:
            image = np.fliplr(image)

        input_image = util.resize_image_by_pil(image, 1 / self.scale)
        input_bicubic_image = util.resize_image_by_pil(input_image, self.scale)

        if max_value != 255:
            scale = max_value / 255.0
            input_image = np.multiply(input_image, scale)
            input_bicubic_image = np.multiply(input_bicubic_image, scale)
            image = np.multiply(image, scale)

        return input_image, input_bicubic_image, image

    def load_random_patch(self, filename):

        image = util.load_image(filename, print_console=False)
        height, width = image.shape[0:2]

        load_batch_size = self.batch_image_size * self.scale

        if height < load_batch_size or width < load_batch_size:
            print("Error: %s should have more than %d x %d size." % (filename, load_batch_size, load_batch_size))
            return None

        if height == load_batch_size:
            y = 0
        else:
            y = random.randrange(height - load_batch_size)

        if width == load_batch_size:
            x = 0
        else:
            x = random.randrange(width - load_batch_size)
        image = image[y:y + load_batch_size, x:x + load_batch_size, :]
        image = build_input_image(image, channels=self.channels, convert_ycbcr=True)

        return image
