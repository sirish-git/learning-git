"""
Paper: "Fast and Accurate Image Super Resolution by Deep CNN with Skip Connection and Network in Network"
Ver: 2.0

DCSCN model implementation (Transposed-CNN / Pixel Shuffler version)
See Detail: https://github.com/jiny2001/dcscn-super-resolution/

Please note this model is updated version of the paper.
If you want to check original source code and results of the paper, please see https://github.com/jiny2001/dcscn-super-resolution/tree/ver1.

Additional support for using depthwise separable convolutions in place of each convolutional layer was provided by Chew Jing Wei
(https://github.com/tehtea).
"""

import logging
import math
import os
import time

import numpy as np
import tensorflow as tf
import cv2

from helper import loader, tf_graph, utilty as util

BICUBIC_METHOD_STRING = "bicubic"


class SuperResolution(tf_graph.TensorflowGraph):
    def __init__(self, flags, model_name=""):

        super().__init__(flags)

        # custom architecture flag
        self.arch_type = flags.arch_type
        		
        # Model Parameters
        self.scale = flags.scale
        self.layers = flags.layers
        self.filters = flags.filters
        self.min_filters = min(flags.filters, flags.min_filters)
        self.filters_decay_gamma = flags.filters_decay_gamma
        self.use_nin = flags.use_nin
        self.nin_filters = flags.nin_filters
        self.nin_filters2 = flags.nin_filters2
        self.reconstruct_layers = max(flags.reconstruct_layers, 1)
        self.reconstruct_filters = flags.reconstruct_filters
        self.resampling_method = BICUBIC_METHOD_STRING
        self.pixel_shuffler = flags.pixel_shuffler
        self.pixel_shuffler_filters = flags.pixel_shuffler_filters
        self.self_ensemble = flags.self_ensemble
        self.depthwise_separable = flags.depthwise_separable
        
        # Training Parameters
        self.l2_decay = flags.l2_decay
        self.optimizer = flags.optimizer
        self.beta1 = flags.beta1
        self.beta2 = flags.beta2
        self.epsilon = flags.epsilon
        self.momentum = flags.momentum
        self.batch_num = flags.batch_num
        self.batch_image_size = flags.batch_image_size
        if flags.stride_size == 0:
            self.stride_size = flags.batch_image_size // 2
        else:
            self.stride_size = flags.stride_size
        self.patches_cnt = flags.patches_cnt
        self.clipping_norm = flags.clipping_norm
        self.use_l1_loss = flags.use_l1_loss

        # Learning Rate Control for Training
        self.initial_lr = flags.initial_lr
        self.lr_decay = flags.lr_decay
        self.lr_decay_epoch = flags.lr_decay_epoch
        # warm_up lr params
        self.warm_up = flags.warm_up
        self.warm_up_lr = flags.warm_up_lr
        # restart lr params
        self.restart_lr_cnt = flags.restart_lr_cnt
        if flags.restart_lr_cnt > 0:
            # override actual lr decay
            self.lr_decay_epoch = flags.restart_lr_decay_epoch
            self.restart_lr_decay_epoch = flags.restart_lr_decay_epoch
            self.restart_lr_threshold = flags.restart_lr_threshold
            if flags.restart_lr == 0.0:
                # init with initial lr
                self.restart_lr = flags.initial_lr * 0.5
            else:
                self.restart_lr = flags.restart_lr
        # number of batches with given train images, batch_num and warmp epochs
        batch_cnt_epoch = (flags.training_images / flags.batch_num) * flags.warm_up_epochs
        self.warm_up_lr_step = (self.initial_lr - self.warm_up_lr) / batch_cnt_epoch

        # Dataset or Others
        self.training_images = int(math.ceil(flags.training_images / flags.batch_num) * flags.batch_num)
        self.train = None
        self.test = None
        self.compress_input_q = flags.compress_input_q

        # Image Processing Parameters
        self.max_value = flags.max_value
        self.channels = flags.channels
        # make input and output channels count same
        self.output_channels = 1
        self.psnr_calc_border_size = flags.psnr_calc_border_size
        if self.psnr_calc_border_size < 0:
            self.psnr_calc_border_size = self.scale

        # Environment (all directory name should not contain tailing '/'  )
        self.batch_dir = flags.batch_dir

        # initialize variables
        self.name = self.get_model_name(model_name)
        self.total_epochs = 0
        lr = self.initial_lr
        while lr > flags.end_lr:
            self.total_epochs += self.lr_decay_epoch
            lr *= self.lr_decay

        # initialize environment
        #util.make_dir(self.checkpoint_dir)
        util.make_dir(flags.graph_dir)
        util.make_dir(self.tf_log_dir)
        if flags.initialize_tf_log:
            util.clean_dir(self.tf_log_dir)
        # remove existing log file
        if os.path.exists(flags.log_filename):        
            os.remove(flags.log_filename)
        # set and start logging
        util.set_logging(flags.log_filename, stream_log_level=logging.INFO, file_log_level=logging.INFO,
                         tf_log_level=tf.logging.WARN)
        logging.info("\n [%s] -------------------------------------" % (self.arch_type))
        logging.info("%s [%s]" % (util.get_now_date(), self.name))

        self.init_train_step()
        
    def create_model_dir(self):
        self.create_checkpoint_dir(self.scale)

    def get_model_name(self, model_name, name_postfix=""):
        if model_name is "":
            name = self.arch_type + "_" + "{}x_".format(self.scale)
        else:
            name = "%s" % model_name

        return name

    def load_dynamic_datasets(self, data_dir, batch_image_size):
        """ loads datasets
        Opens image directory as a datasets. Images will be loaded when build_input_batch() is called.
        """

        self.train = loader.DynamicDataSets(self.scale, batch_image_size, channels=self.channels,
                                            resampling_method=self.resampling_method)
        self.train.set_data_dir(data_dir)

    def load_datasets(self, data_dir, batch_dir, batch_image_size, stride_size=0):
        """ build input patch images and loads as a datasets
        Opens image directory as a datasets.
        Each images are splitted into patch images and converted to input image. Since loading
        (especially from PNG/JPG) and building input-LR images needs much computation in the
        training phase, building pre-processed images makes training much faster. However, images
        are limited by divided grids.
        """

        batch_dir += "/scale%d" % self.scale
        
        self.train = loader.BatchDataSets(self.scale, batch_dir, batch_image_size, stride_size, channels=self.channels,
                                          resampling_method=self.resampling_method, patches_cnt=self.patches_cnt, compress_input_q=self.compress_input_q)

        self.train.build_batch(data_dir)
        #if not self.train.is_batch_exist():
        #    self.train.build_batch(data_dir)
        #else:
        #    self.train.load_batch_counts()
        #self.train.load_all_batch_images()

    def init_epoch_index(self):

        self.batch_input = self.batch_num * [None]
        self.batch_input_bicubic = self.batch_num * [None]
        self.batch_true = self.batch_num * [None]

        self.training_psnr_sum = 0
        self.training_loss_sum = 0
        self.training_step = 0
        self.train.init_batch_index()

    def build_input_batch(self):

        for i in range(self.batch_num):
            self.batch_input[i], self.batch_input_bicubic[i], self.batch_true[i] = self.train.load_batch_image(
                self.max_value)

    def load_graph(self, frozen_graph_filename='./model_to_freeze/frozen_model_optimized.pb'):
        """ 
        load an existing frozen graph into the current graph.
        """
        # self.name =  "frozen_model" #TODO: Generalise this line

        # We load the protobuf file from the disk and parse it to retrieve the 
        # unserialized graph_def
        with tf.gfile.GFile(frozen_graph_filename, "rb") as f:
            graph_def = tf.GraphDef()
            graph_def.ParseFromString(f.read())

         # load the graph def into the current graph
        with self.as_default() as graph:
            tf.import_graph_def(graph_def, name="prefix")

        self.is_training = tf.placeholder(tf.bool, name="is_training")

        # get input and output tensors

         # input
        self.x = self.get_tensor_by_name("prefix/x:0")
        self.x2 = self.get_tensor_by_name("prefix/x2:0")
        if self.dropout_rate < 1:
            self.dropout = self.get_tensor_by_name("prefix/dropout_keep_rate:0")

         # output
        self.y_ = self.get_tensor_by_name('prefix/output:0')

         # close existing session and re-initialize it
        self.sess.close()
        super().init_session()

    def build_graph_dcscn(self):

        self.x = tf.placeholder(tf.float32, shape=[None, None, None, self.channels], name="x")
        self.y = tf.placeholder(tf.float32, shape=[None, None, None, self.output_channels], name="y")
        self.x2 = tf.placeholder(tf.float32, shape=[None, None, None, self.output_channels], name="x2")
        self.dropout = tf.placeholder(tf.float32, shape=[], name="dropout_keep_rate")
        self.is_training = tf.placeholder(tf.bool, name="is_training")

        # building feature extraction layers

        output_feature_num = self.filters
        total_output_feature_num = 0
        input_feature_num = self.channels
        input_tensor = self.x		

        if self.save_weights:
            with tf.name_scope("X"):
                util.add_summaries("output", self.name, self.x, save_stddev=True, save_mean=True)

        for i in range(self.layers):
            if self.min_filters != 0 and i > 0:
                x1 = i / float(self.layers - 1)
                y1 = pow(x1, 1.0 / self.filters_decay_gamma)
                output_feature_num = int((self.filters - self.min_filters) * (1 - y1) + self.min_filters)
					
            if (self.depthwise_separable):
                self.build_depthwise_separable_conv("CNN%d" % (i + 1), input_tensor, self.cnn_size, self.cnn_size, input_feature_num,
                                            output_feature_num, use_bias=True, activator=self.activator,
                                            use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)
            else:					                        					
                self.build_conv("CNN%d" % (i + 1), input_tensor, self.cnn_size, self.cnn_size, input_feature_num,
                                output_feature_num, use_bias=True, activator=self.activator,
                                use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)
					
            input_feature_num = output_feature_num
            input_tensor = self.H[-1]
            total_output_feature_num += output_feature_num

        with tf.variable_scope("Concat"):
            self.H_concat = tf.concat(self.H, 3, name="H_concat")
        self.features += " Total: (%d)" % total_output_feature_num

        # building reconstruction layers ---

        if self.use_nin:
            if (self.depthwise_separable):
                self.build_depthwise_separable_conv("A1", self.H_concat, 1, 1, total_output_feature_num, self.nin_filters,
                            dropout_rate=self.dropout_rate, use_bias=True, activator=self.activator)
                self.receptive_fields -= (self.cnn_size - 1)
                self.build_depthwise_separable_conv("B1", self.H_concat, 1, 1, total_output_feature_num, self.nin_filters2,
                                dropout_rate=self.dropout_rate, use_bias=True, activator=self.activator)
                self.build_depthwise_separable_conv("B2", self.H[-1], 3, 3, self.nin_filters2, self.nin_filters2,
                                dropout_rate=self.dropout_rate, use_bias=True, activator=self.activator)
            else:
                self.build_conv("A1", self.H_concat, 1, 1, total_output_feature_num, self.nin_filters,
                            dropout_rate=self.dropout_rate, use_bias=True, activator=self.activator)
                self.receptive_fields -= (self.cnn_size - 1)
                self.build_conv("B1", self.H_concat, 1, 1, total_output_feature_num, self.nin_filters2,
                                dropout_rate=self.dropout_rate, use_bias=True, activator=self.activator)
                self.build_conv("B2", self.H[-1], 3, 3, self.nin_filters2, self.nin_filters2,
                                dropout_rate=self.dropout_rate, use_bias=True, activator=self.activator)

            self.H.append(tf.concat([self.H[-1], self.H[-3]], 3, name="Concat2"))
            input_channels = self.nin_filters + self.nin_filters2
        else:
            if (self.depthwise_separable):
                self.build_depthwise_separable_conv("C", self.H_concat, 1, 1, total_output_feature_num, self.filters,
                    dropout_rate=self.dropout_rate, use_bias=True, activator=self.activator)
            else:
                self.build_conv("C", self.H_concat, 1, 1, total_output_feature_num, self.filters,
                    dropout_rate=self.dropout_rate, use_bias=True, activator=self.activator)
            input_channels = self.filters

        # building upsampling layer
        if self.pixel_shuffler:
            if self.pixel_shuffler_filters != 0:
                output_channels = self.pixel_shuffler_filters
            else:
                output_channels = input_channels
            if self.scale == 4:
                self.build_pixel_shuffler_layer("Up-PS", self.H[-1], 2, 
                                                input_channels, input_channels, 
                                                depthwise_separable=self.depthwise_separable)
                self.build_pixel_shuffler_layer("Up-PS2", self.H[-1], 2, 
                                                input_channels, output_channels, 
                                                depthwise_separable=self.depthwise_separable)
            else:
                self.build_pixel_shuffler_layer("Up-PS", self.H[-1], self.scale, 
                                                input_channels, output_channels, 
                                                depthwise_separable=self.depthwise_separable)
            input_channels = output_channels
        else:
            self.build_transposed_conv("Up-TCNN", self.H[-1], self.scale, input_channels)

        for i in range(self.reconstruct_layers - 1):
            self.build_conv("R-CNN%d" % (i + 1), self.H[-1], self.cnn_size, self.cnn_size, input_channels, self.reconstruct_filters,
                            dropout_rate=self.dropout_rate, use_bias=True, activator=self.activator)
            input_channels = self.reconstruct_filters

        if (self.depthwise_separable):
            self.build_depthwise_separable_conv("R-CNN%d" % self.reconstruct_layers, self.H[-1], 
                        self.cnn_size, self.cnn_size, input_channels, self.output_channels)
        else:
            self.build_conv("R-CNN%d" % self.reconstruct_layers, self.H[-1], self.cnn_size, self.cnn_size, input_channels,
                        self.output_channels)

        self.y_ = tf.add(self.H[-1], self.x2, name="output")

        if self.save_weights:
            with tf.name_scope("Y_"):
                util.add_summaries("output", self.name, self.y_, save_stddev=True, save_mean=True)					

    # 1x3 and 3x1 layers followed by conv layer in each branch and concatanate    
    def edge_synth_block_type1(self, inp, i, edge_layers=1, inp_ch=16, out_ch_middle=8, out_ch_final=16, normal_conv_branch=0):
    
        if normal_conv_branch==1:
            # conv        
            i = i + 1
            out100 = self.build_depthwise_separable_conv("CNN%d" % (i), inp, 3, 3, inp_ch, out_ch_middle, use_bias=True, activator=self.activator,
                                use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)        
            i = i + 1
            out101 = self.build_depthwise_separable_conv("CNN%d" % (i), out100, 3, 3, out_ch_middle, out_ch_middle, use_bias=True, activator=self.activator,
                                use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)            
    
        # conv        
        i = i + 1
        out1 = self.build_conv("CNN%d" % (i), inp, 1, 3, inp_ch, out_ch_middle, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate) 
        # edge layers (M in paper)
        for j in range(edge_layers-1):
            out1 = self.build_conv("CNN%d" % (i), out1, 1, 3, out_ch_middle, out_ch_middle, use_bias=True, activator=self.activator,
                                use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate) 
                               
        # conv dep sep
        i = i + 1
        out1_1 = self.build_depthwise_separable_conv("CNN%d" % (i), out1, 3, 3, out_ch_middle, out_ch_middle, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate) 
                               
        # conv        
        i = i + 1
        out2 = self.build_conv("CNN%d" % (i), inp, 3, 1, inp_ch, out_ch_middle, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)                           
        # edge layers (M in paper)
        for j in range(edge_layers-1):
            out2 = self.build_conv("CNN%d" % (i), out2, 3, 1, out_ch_middle, out_ch_middle, use_bias=True, activator=self.activator,
                                use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)                     
                     
        # conv dep sep
        i = i + 1
        out2_2 = self.build_depthwise_separable_conv("CNN%d" % (i), out2, 3, 3, out_ch_middle, out_ch_middle, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate) 
                 
        # concat
        inp_chn = out_ch_middle*2
        if normal_conv_branch==1:
            inp_chn = out_ch_middle*3
            out3 = tf.concat((out1_1, out2_2, out101), 3, name="feature_concat") 
        else:
            out3 = tf.concat((out1_1, out2_2), 3, name="feature_concat") 
        
        # conv dep sep
        i = i + 1
        out4 = self.build_depthwise_separable_conv("CNN%d" % (i), out3, 3, 3, inp_chn, out_ch_final, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)         
                               
        return out4, i

    # 1x3 and 3x1 layers followed by conv layer in each branch and concatanate    
    def edge_synth_block_type2(self, inp, i, inp_ch, out_ch, kh, kw, layer_type='conv_dep_sep'):
    
        if layer_type=='conv_dep_sep':
            # conv        
            i = i + 1
            out1 = self.build_conv_atrous("CNN%d" % (i), inp, kh, kw, inp_ch, out_ch, use_bias=True, activator=self.activator,
                                use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate, dilate_stride=4) 
                    
            # conv
            i = i + 1
            out1_1 = self.build_depthwise_separable_conv("CNN%d" % (i), out1, kh, kw, out_ch, out_ch, use_bias=True, activator=self.activator,
                                use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate) 
                                
            # conv        
            i = i + 1
            out1_2 = self.build_depthwise_separable_conv("CNN%d" % (i), out1_1, kh, kw, out_ch, out_ch, use_bias=True, activator=self.activator,
                                use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)                                                
                    
            # concat
            out3 = tf.concat((out1, out1_2), 3, name="feature_concat") 
    
            # conv dep sep
            i = i + 1
            out4 = self.build_depthwise_separable_conv("CNN%d" % (i), out3, kh, kw, out_ch*2, out_ch, use_bias=True, activator=self.activator,
                                use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)                
        elif layer_type=='conv_normal':
            # conv        
            i = i + 1
            out1 = self.build_conv_atrous("CNN%d" % (i), inp, kh, kw, inp_ch, out_ch, use_bias=True, activator=self.activator,
                                use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate, dilate_stride=4) 
                    
            # conv
            i = i + 1
            out1_1 = self.build_conv("CNN%d" % (i), out1, kh, kw, out_ch, out_ch, use_bias=True, activator=self.activator,
                                use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate) 
                                
            # conv        
            i = i + 1
            out1_2 = self.build_conv("CNN%d" % (i), out1_1, kh, kw, out_ch, out_ch, use_bias=True, activator=self.activator,
                                use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)                                                
                    
            # concat
            out3 = tf.concat((out1, out1_2), 3, name="feature_concat") 
    
            # conv dep sep
            i = i + 1
            out4 = self.build_conv("CNN%d" % (i), out3, kh, kw, out_ch*2, out_ch, use_bias=True, activator=self.activator,
                                use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)         
                                
        return out4, i        
                
    '''
    # Architecture description:
    # Model released to AI Zoom
    # 1x3 and 3x1 block structure with concatenation
    '''                
    def build_graph_v1_edge_concat(self):

        self.x = tf.placeholder(tf.float32, shape=[None, None, None, self.channels], name="x")
        self.y = tf.placeholder(tf.float32, shape=[None, None, None, self.output_channels], name="y")
        self.x2 = tf.placeholder(tf.float32, shape=[None, None, None, self.output_channels], name="x2")
        self.dropout = tf.placeholder(tf.float32, shape=[], name="dropout_keep_rate")
        self.is_training = tf.placeholder(tf.bool, name="is_training")

        # building feature extraction layers

        output_feature_num = self.filters
        total_output_feature_num = 0
        input_feature_num = self.channels
        input_tensor = self.x
		
        # custom architecture
        i = 0	

        if self.save_weights:
            with tf.name_scope("X"):
                util.add_summaries("output", self.name, self.x, save_stddev=True, save_mean=True)

        # [3x3x1x16]    
        i = i + 1        
        out1 = self.build_conv("CNN%d" % (i), input_tensor, 3, 3, input_feature_num, 16, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)                
                               
        # [1x3x16x16]      
        i = i + 1
        out2 = self.build_conv("CNN%d" % (i), out1, 1, 3, 16, 8, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)                               

        # [3x1x16x16]      
        i = i + 1
        out3 = self.build_conv("CNN%d" % (i), out1, 3, 1, 16, 8, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate) 
                                                       
        # concat
        out4 = tf.concat((out2, out3), 3, name="feature_concat")                                                                   
                  
        # [3x3x16x8]       
        i = i + 1
        out5 = self.build_conv("CNN%d" % (i), out4, 3, 3, 16, 8, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)  
                       
        # concat
        out6 = tf.concat((out1, out5), 3, name="feature_concat")    
        
        # dimension reduction
        # [1x1x24x16]        
        i = i + 1
        out7 = self.build_conv("CNN%d" % (i), out6, 1, 3, 24, 8, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate) 
                               
        # [1x1x24x16]        
        i = i + 1
        out8 = self.build_conv("CNN%d" % (i), out6, 3, 1, 24, 8, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)                           
                    
        # concat
        out10 = tf.concat((out6, out7, out8), 3, name="feature_concat")        
        
        # dimension reduction
        # [1x1x24x16]  
        out_ch_num = 32    
        i = i + 1
        out11 = self.build_depthwise_separable_conv("CNN%d" % (i), out10, 3, 3, 40, out_ch_num, use_bias=True, activator=self.activator,
                                    use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)         
                                                  
        # building upsampling layer
        if self.scale == 1:
            # for AR network
            out12 = out11
        else:
            # for SR network
            out12 = tf.depth_to_space(out11, self.scale)
        #update input pixels after calling depth to space
        self.pix_per_input = self.scale
        
        # compute the channels appropriately based on scale and depth2space        
        inp_ch_num = out_ch_num // (self.scale * self.scale)
        # [3x3x16x8]
        i = i + 1
        out11 = self.build_conv("CNN%d" % (i), out12, 3, 3, inp_ch_num, 1, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)  

        # global residual
        self.y_ = tf.add(self.H[-1], self.x2, name="output")

        if self.save_weights:
            with tf.name_scope("Y_"):
                util.add_summaries("output", self.name, self.y_, save_stddev=True, save_mean=True)	        
    
    '''
    # Architecture description:
    # 1x3 and 3x1 block structure with concatenation
    # similar to v1, with extra 16x8 in 2nd structure block also
    
    +++++++++ To be published +++++++++++
    '''   
    def build_graph_v2_edge_concat(self):

        self.x = tf.placeholder(tf.float32, shape=[None, None, None, self.channels], name="x")
        self.y = tf.placeholder(tf.float32, shape=[None, None, None, self.output_channels], name="y")
        self.x2 = tf.placeholder(tf.float32, shape=[None, None, None, self.output_channels], name="x2")
        self.dropout = tf.placeholder(tf.float32, shape=[], name="dropout_keep_rate")
        self.is_training = tf.placeholder(tf.bool, name="is_training")

        # building feature extraction layers

        output_feature_num = self.filters
        total_output_feature_num = 0
        input_feature_num = self.channels
        input_tensor = self.x
		
        # custom architecture
        i = 0	

        if self.save_weights:
            with tf.name_scope("X"):
                util.add_summaries("output", self.name, self.x, save_stddev=True, save_mean=True)

        # [3x3x1x16]    
        i = i + 1        
        out1 = self.build_conv("CNN%d" % (i), input_tensor, 3, 3, input_feature_num, 16, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)                
                               
        # [1x3x16x16]      
        i = i + 1
        out2 = self.build_conv("CNN%d" % (i), out1, 1, 3, 16, 8, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)                               

        # [3x1x16x16]      
        i = i + 1
        out3 = self.build_conv("CNN%d" % (i), out1, 3, 1, 16, 8, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate) 
                                                       
        # concat
        out4 = tf.concat((out2, out3), 3, name="feature_concat")                                                                   
                  
        # [3x3x16x8]       
        i = i + 1
        out5 = self.build_conv("CNN%d" % (i), out4, 3, 3, 16, 8, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)  
                       
        # concat
        out6 = tf.concat((out1, out5), 3, name="feature_concat")    
        
        # dimension reduction
        # [1x1x24x16]        
        i = i + 1
        out7 = self.build_conv("CNN%d" % (i), out6, 1, 3, 24, 8, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate) 
                               
        # [1x1x24x16]        
        i = i + 1
        out8 = self.build_conv("CNN%d" % (i), out6, 3, 1, 24, 8, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)                           
         
        # concat
        out78 = tf.concat((out7, out8), 3, name="feature_concat") 
        
        # [3x3x16x8]       
        i = i + 1
        out9 = self.build_conv("CNN%d" % (i), out78, 3, 3, 16, 8, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)    
                               
        # concat
        out10 = tf.concat((out6, out9), 3, name="feature_concat")        
        
        # dimension reduction
        # [1x1x24x16]  
        out_ch_num = 32    
        i = i + 1
        out11 = self.build_depthwise_separable_conv("CNN%d" % (i), out10, 3, 3, 32, out_ch_num, use_bias=True, activator=self.activator,
                                    use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)         
                                                  
        # building upsampling layer
        if self.scale == 1:
            # for AR network
            out12 = out11
        else:
            # for SR network        
            out12 = tf.depth_to_space(out11, self.scale)
        #update input pixels after calling depth to space
        self.pix_per_input = self.scale
        
        # compute the channels appropriately based on scale and depth2space        
        inp_ch_num = out_ch_num // (self.scale * self.scale)
        # [3x3x16x8]
        i = i + 1
        out11 = self.build_conv("CNN%d" % (i), out12, 3, 3, inp_ch_num, 1, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)  

        # global residual
        self.y_ = tf.add(self.H[-1], self.x2, name="output")

        if self.save_weights:
            with tf.name_scope("Y_"):
                util.add_summaries("output", self.name, self.y_, save_stddev=True, save_mean=True)	        
                
                
    def build_graph_v3_edge_concat(self):
        self.x = tf.placeholder(tf.float32, shape=[None, None, None, self.channels], name="x")
        self.y = tf.placeholder(tf.float32, shape=[None, None, None, self.output_channels], name="y")
        self.x2 = tf.placeholder(tf.float32, shape=[None, None, None, self.output_channels], name="x2")
        self.dropout = tf.placeholder(tf.float32, shape=[], name="dropout_keep_rate")
        self.is_training = tf.placeholder(tf.bool, name="is_training")

        # building feature extraction layers

        output_feature_num = self.filters
        total_output_feature_num = 0
        input_feature_num = self.channels
        input_tensor = self.x
		
        # custom architecture
        i = 0	

        if self.save_weights:
            with tf.name_scope("X"):
                util.add_summaries("output", self.name, self.x, save_stddev=True, save_mean=True)

        # conv    
        i = i + 1        
        out1 = self.build_conv("CNN%d" % (i), input_tensor, 3, 3, input_feature_num, 16, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)                

        # conv dep-sep  
        i = i + 1
        out100 = self.build_depthwise_separable_conv("CNN%d" % (i), out1, 3, 3, 16, 8, use_bias=True, activator=self.activator,
                                    use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate) 
                                    
        # conv     
        i = i + 1
        out2 = self.build_conv("CNN%d" % (i), out100, 1, 3, 8, 4, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)                               

        # conv     
        i = i + 1
        out3 = self.build_conv("CNN%d" % (i), out100, 3, 1, 8, 4, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate) 
                                                       
        # concat
        out4 = tf.concat((out2, out3), 3, name="feature_concat")                                                                   
                  
        # conv dep-sep      
        i = i + 1
        out5 = self.build_depthwise_separable_conv("CNN%d" % (i), out4, 3, 3, 8, 8, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)  
                       
        # residual
        #out6 = out5 + out100    
        out6 = out5
        
        # conv       
        i = i + 1
        out7 = self.build_conv("CNN%d" % (i), out6, 1, 3, 8, 4, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate) 
                               
        # [1x1x24x16]        
        i = i + 1
        out8 = self.build_conv("CNN%d" % (i), out6, 3, 1, 8, 4, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)                           
         
        # concat
        out78 = tf.concat((out7, out8), 3, name="feature_concat") 
        
        # conv dep-sep       
        i = i + 1
        out9 = self.build_depthwise_separable_conv("CNN%d" % (i), out78, 3, 3, 8, 8, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)    
                               
        # conv dep-sep       
        i = i + 1
        out101 = self.build_depthwise_separable_conv("CNN%d" % (i), out100, 3, 3, 8, 8, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)
                               
        # concat
        out10 = tf.concat((out100, out101, out6, out9), 3, name="feature_concat")                
                               
        # conv dep-sep
        out_ch_num = 32    
        i = i + 1
        out11 = self.build_depthwise_separable_conv("CNN%d" % (i), out10, 3, 3, 32, out_ch_num, use_bias=True, activator=self.activator,
                                    use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)         
                                                  
        # building upsampling layer
        if self.scale == 1:
            # for AR network
            out12 = out11
        else:
            # for SR network        
            out12 = tf.depth_to_space(out11, self.scale)
        #update input pixels after calling depth to space
        self.pix_per_input = self.scale
        
        # compute the channels appropriately based on scale and depth2space        
        inp_ch_num = out_ch_num // (self.scale * self.scale)
        # [3x3x16x8]
        i = i + 1
        out11 = self.build_conv("CNN%d" % (i), out12, 3, 3, inp_ch_num, 1, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)  

        # global residual
        self.y_ = tf.add(self.H[-1], self.x2, name="output")

        if self.save_weights:
            with tf.name_scope("Y_"):
                util.add_summaries("output", self.name, self.y_, save_stddev=True, save_mean=True)	        

    def build_graph_v4_edge_concat(self):
        self.x = tf.placeholder(tf.float32, shape=[None, None, None, self.channels], name="x")
        self.y = tf.placeholder(tf.float32, shape=[None, None, None, self.output_channels], name="y")
        self.x2 = tf.placeholder(tf.float32, shape=[None, None, None, self.output_channels], name="x2")
        self.dropout = tf.placeholder(tf.float32, shape=[], name="dropout_keep_rate")
        self.is_training = tf.placeholder(tf.bool, name="is_training")

        # building feature extraction layers

        output_feature_num = self.filters
        total_output_feature_num = 0
        input_feature_num = self.channels
        input_tensor = self.x
		
        # custom architecture
        i = 0	

        if self.save_weights:
            with tf.name_scope("X"):
                util.add_summaries("output", self.name, self.x, save_stddev=True, save_mean=True)

        # conv    
        i = i + 1        
        out1 = self.build_conv("CNN%d" % (i), input_tensor, 3, 3, input_feature_num, 16, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)                

        # conv dep-sep  
        i = i + 1
        out100 = self.build_depthwise_separable_conv("CNN%d" % (i), out1, 3, 3, 16, 8, use_bias=True, activator=self.activator,
                                    use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate) 
                                    
        # conv     
        i = i + 1
        out2 = self.build_conv("CNN%d" % (i), out100, 1, 3, 8, 4, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)                               

        # conv     
        i = i + 1
        out3 = self.build_conv("CNN%d" % (i), out100, 3, 1, 8, 4, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate) 
                                                       
        # concat
        out4 = tf.concat((out2, out3), 3, name="feature_concat")                                                                   
                  
        # conv dep-sep      
        i = i + 1
        out5 = self.build_depthwise_separable_conv("CNN%d" % (i), out4, 3, 3, 8, 8, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)  
 
        # conv dep-sep      
        i = i + 1
        out51 = self.build_depthwise_separable_conv("CNN%d" % (i), out5, 3, 3, 8, 8, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)  

        # conv dep-sep      
        i = i + 1
        out52 = self.build_depthwise_separable_conv("CNN%d" % (i), out5, 3, 3, 8, 8, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)  

        # concat
        out6 = tf.concat((out51, out52), 3, name="feature_concat")                                          
                               
        # conv dep-sep       
        i = i + 1
        out101 = self.build_depthwise_separable_conv("CNN%d" % (i), out100, 3, 3, 8, 8, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)
                               
        # concat
        out10 = tf.concat((out101, out5), 3, name="feature_concat")                
                               
        # conv dep-sep  
        i = i + 1
        out102 = self.build_depthwise_separable_conv("CNN%d" % (i), out10, 3, 3, 16, 16, use_bias=True, activator=self.activator,
                                    use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)    

        # conv dep-sep  
        i = i + 1
        out103 = self.build_depthwise_separable_conv("CNN%d" % (i), out6, 3, 3, 16, 16, use_bias=True, activator=self.activator,
                                    use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)                                     

        # concat
        out11 = tf.concat((out102, out103), 3, name="feature_concat")                                       
        out_ch_num = 32                                      
        
        # building upsampling layer
        if self.scale == 1:
            # for AR network
            out12 = out11
        else:
            # for SR network        
            out12 = tf.depth_to_space(out11, self.scale)
        #update input pixels after calling depth to space
        self.pix_per_input = self.scale
        
        # compute the channels appropriately based on scale and depth2space        
        inp_ch_num = out_ch_num // (self.scale * self.scale)
        # [3x3x16x8]
        i = i + 1
        out11 = self.build_conv("CNN%d" % (i), out12, 3, 3, inp_ch_num, 1, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)  

        # global residual
        self.y_ = tf.add(self.H[-1], self.x2, name="output")

        if self.save_weights:
            with tf.name_scope("Y_"):
                util.add_summaries("output", self.name, self.y_, save_stddev=True, save_mean=True)	        
        
    '''
    # Architecture description:
    # Architecture as a combination of v1 and v3, with ~5k mac
    '''                
    def build_graph_v5_edge_concat(self):

        self.x = tf.placeholder(tf.float32, shape=[None, None, None, self.channels], name="x")
        self.y = tf.placeholder(tf.float32, shape=[None, None, None, self.output_channels], name="y")
        self.x2 = tf.placeholder(tf.float32, shape=[None, None, None, self.output_channels], name="x2")
        self.dropout = tf.placeholder(tf.float32, shape=[], name="dropout_keep_rate")
        self.is_training = tf.placeholder(tf.bool, name="is_training")

        # building feature extraction layers

        output_feature_num = self.filters
        total_output_feature_num = 0
        input_feature_num = self.channels
        input_tensor = self.x
		
        # custom architecture
        i = 0	

        if self.save_weights:
            with tf.name_scope("X"):
                util.add_summaries("output", self.name, self.x, save_stddev=True, save_mean=True)

        # conv    
        i = i + 1        
        out1 = self.build_conv("CNN%d" % (i), input_tensor, 3, 3, input_feature_num, 16, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)                
                               
        # conv
        i = i + 1
        out1_1 = self.build_conv("CNN%d" % (i), out1, 1, 3, 16, 8, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)                               

        # conv
        i = i + 1
        out1_2 = self.build_conv("CNN%d" % (i), out1, 3, 1, 16, 8, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate) 
                                                       
        # concat
        out4 = tf.concat((out1_1, out1_2), 3, name="feature_concat")                                                                   
                  
        # conv dep sep       
        i = i + 1
        out5 = self.build_depthwise_separable_conv("CNN%d" % (i), out4, 3, 3, 16, 16, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)  
                       
        # concat
        out6 = tf.concat((out1, out5), 3, name="feature_concat")    
        
        # conv dep sep
        i = i + 1
        out7 = self.build_depthwise_separable_conv("CNN%d" % (i), out6, 3, 3, 32, 16, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate) 

        # conv        
        i = i + 1
        out7_1 = self.build_conv("CNN%d" % (i), out7, 1, 3, 16, 8, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate) 
                   
        # conv dep sep
        i = i + 1
        out7_1 = self.build_depthwise_separable_conv("CNN%d" % (i), out7_1, 3, 3, 8, 8, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate) 
                               
        # conv        
        i = i + 1
        out7_2 = self.build_conv("CNN%d" % (i), out7, 3, 1, 16, 8, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)                           
                     
        # conv dep sep
        i = i + 1
        out7_2 = self.build_depthwise_separable_conv("CNN%d" % (i), out7_2, 3, 3, 8, 8, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate) 
                 
        # concat
        out8 = tf.concat((out7_1, out7_2), 3, name="feature_concat") 

        # conv dep sep
        i = i + 1
        out9 = self.build_depthwise_separable_conv("CNN%d" % (i), out8, 3, 3, 16, 16, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)         
        
        # concat
        out10 = tf.concat((out7, out9), 3, name="feature_concat")        
        
        # dimension reduction
        # [1x1x24x16]  
        out_ch_num = 32    
        i = i + 1
        out11 = self.build_depthwise_separable_conv("CNN%d" % (i), out10, 3, 3, 32, out_ch_num, use_bias=True, activator=self.activator,
                                    use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)         
                                                  
        # building upsampling layer
        if self.scale == 1:
            # for AR network
            out12 = out11
        else:
            # for SR network        
            out12 = tf.depth_to_space(out11, self.scale)
        #update input pixels after calling depth to space
        self.pix_per_input = self.scale
        
        # compute the channels appropriately based on scale and depth2space        
        inp_ch_num = out_ch_num // (self.scale * self.scale)
        # [3x3x16x8]
        i = i + 1
        out11 = self.build_conv("CNN%d" % (i), out12, 3, 3, inp_ch_num, 1, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)  

        # global residual
        self.y_ = tf.add(self.H[-1], self.x2, name="output")

        if self.save_weights:
            with tf.name_scope("Y_"):
                util.add_summaries("output", self.name, self.y_, save_stddev=True, save_mean=True)	        
                
    def build_graph_v5_rzn_l(self):

        self.x = tf.placeholder(tf.float32, shape=[None, None, None, self.channels], name="x")
        self.y = tf.placeholder(tf.float32, shape=[None, None, None, self.output_channels], name="y")
        self.x2 = tf.placeholder(tf.float32, shape=[None, None, None, self.output_channels], name="x2")
        self.dropout = tf.placeholder(tf.float32, shape=[], name="dropout_keep_rate")
        self.is_training = tf.placeholder(tf.bool, name="is_training")

        # building feature extraction layers

        output_feature_num = self.filters
        total_output_feature_num = 0
        input_feature_num = self.channels
        input_tensor = self.x
		
        # custom architecture
        i = 0	

        if self.save_weights:
            with tf.name_scope("X"):
                util.add_summaries("output", self.name, self.x, save_stddev=True, save_mean=True)
            
        # conv    
        i = i + 1    
        out1 = self.build_conv("CNN%d" % (i), input_tensor, 3, 3, input_feature_num, 16, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)                        
                
        # conv    
        i = i + 1        
        out1 = self.build_depthwise_separable_conv("CNN%d" % (i), out1, 3, 3, 16, 16, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)   
                               
        # edge synthesis block
        out5, i = self.edge_synth_block_type1(out1, i, edge_layers=1, inp_ch=16, out_ch_middle=8, out_ch_final=16, normal_conv_branch=0)
                       
        # concat
        out6 = tf.concat((out1, out5), 3, name="feature_concat")    
        
        # conv dep sep
        i = i + 1
        out7 = self.build_depthwise_separable_conv("CNN%d" % (i), out6, 3, 3, 32, 16, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate) 

        # edge synthesis block
        out9, i = self.edge_synth_block_type1(out7, i, edge_layers=1, inp_ch=16, out_ch_middle=8, out_ch_final=16, normal_conv_branch=0)        
     
        # concat
        out10 = tf.concat((out7, out9), 3, name="feature_concat")        
        inp_ch = 32
        
        # dimension reduction
        # [1x1x24x16]  
        out_ch_num = 32    
        if self.scale == 3:   
            out_ch_num = 36        
        i = i + 1
        out11 = self.build_depthwise_separable_conv("CNN%d" % (i), out10, 3, 3, inp_ch, out_ch_num, use_bias=True, activator=self.activator,
                                    use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)         
                                                  
        # building upsampling layer
        if self.scale == 1:
            # for AR network
            out12 = out11
        else:
            # for SR network        
            out12 = tf.depth_to_space(out11, self.scale)
        #update input pixels after calling depth to space
        self.pix_per_input = self.scale
        
        # compute the channels appropriately based on scale and depth2space        
        inp_ch_num = out_ch_num // (self.scale * self.scale)
        # [3x3x16x8]
        i = i + 1
        out11 = self.build_conv("CNN%d" % (i), out12, 3, 3, inp_ch_num, 1, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)  

        # global residual
        self.y_ = tf.add(self.H[-1], self.x2, name="output")

        if self.save_weights:
            with tf.name_scope("Y_"):
                util.add_summaries("output", self.name, self.y_, save_stddev=True, save_mean=True)	        

    def build_graph_v5_rzn_ul(self):

        self.x = tf.placeholder(tf.float32, shape=[None, None, None, self.channels], name="x")
        self.y = tf.placeholder(tf.float32, shape=[None, None, None, self.output_channels], name="y")
        self.x2 = tf.placeholder(tf.float32, shape=[None, None, None, self.output_channels], name="x2")
        self.dropout = tf.placeholder(tf.float32, shape=[], name="dropout_keep_rate")
        self.is_training = tf.placeholder(tf.bool, name="is_training")

        # building feature extraction layers

        output_feature_num = self.filters
        total_output_feature_num = 0
        input_feature_num = self.channels
        input_tensor = self.x
		
        # custom architecture
        i = 0	

        if self.save_weights:
            with tf.name_scope("X"):
                util.add_summaries("output", self.name, self.x, save_stddev=True, save_mean=True)

        # conv    
        i = i + 1    
        out1 = self.build_conv("CNN%d" % (i), input_tensor, 3, 3, input_feature_num, 16, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)                        
                
        # conv    
        i = i + 1        
        out1 = self.build_depthwise_separable_conv("CNN%d" % (i), out1, 3, 3, 16, 8, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)   
                               
        # edge synthesis block
        out5, i = self.edge_synth_block_type1(out1, i, edge_layers=1, inp_ch=8, out_ch_middle=8, out_ch_final=8, normal_conv_branch=0)
                       
        # concat
        out6 = tf.concat((out1, out5), 3, name="feature_concat")    
        
        # conv dep sep
        i = i + 1
        out7 = self.build_depthwise_separable_conv("CNN%d" % (i), out6, 3, 3, 16, 8, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate) 

        # edge synthesis block
        out9, i = self.edge_synth_block_type1(out7, i, edge_layers=1, inp_ch=8, out_ch_middle=4, out_ch_final=8, normal_conv_branch=0)
     
        # concat
        out10 = tf.concat((out7, out9), 3, name="feature_concat")        
        
        # dimension reduction
        # [1x1x24x16]  
        out_ch_num = 32 
        if self.scale == 3:   
            out_ch_num = 36
        i = i + 1
        out11 = self.build_depthwise_separable_conv("CNN%d" % (i), out10, 3, 3, 16, out_ch_num, use_bias=True, activator=self.activator,
                                    use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)         
                                                  
        # building upsampling layer
        if self.scale == 1:
            # for AR network
            out12 = out11
        else:
            # for SR network        
            out12 = tf.depth_to_space(out11, self.scale)
        #update input pixels after calling depth to space
        self.pix_per_input = self.scale
        
        # compute the channels appropriately based on scale and depth2space        
        inp_ch_num = out_ch_num // (self.scale * self.scale)
        # [3x3x16x8]
        i = i + 1
        out11 = self.build_conv("CNN%d" % (i), out12, 3, 3, inp_ch_num, 1, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)  

        # global residual
        self.y_ = tf.add(self.H[-1], self.x2, name="output")

        if self.save_weights:
            with tf.name_scope("Y_"):
                util.add_summaries("output", self.name, self.y_, save_stddev=True, save_mean=True)	        
                
                
    def build_graph_v5_rzn(self):

        self.x = tf.placeholder(tf.float32, shape=[None, None, None, self.channels], name="x")
        self.y = tf.placeholder(tf.float32, shape=[None, None, None, self.output_channels], name="y")
        self.x2 = tf.placeholder(tf.float32, shape=[None, None, None, self.output_channels], name="x2")
        self.dropout = tf.placeholder(tf.float32, shape=[], name="dropout_keep_rate")
        self.is_training = tf.placeholder(tf.bool, name="is_training")

        # building feature extraction layers

        output_feature_num = self.filters
        total_output_feature_num = 0
        input_feature_num = self.channels
        input_tensor = self.x
		
        # custom architecture
        i = 0	

        if self.save_weights:
            with tf.name_scope("X"):
                util.add_summaries("output", self.name, self.x, save_stddev=True, save_mean=True)

        # conv    
        i = i + 1        
        out1 = self.build_conv("CNN%d" % (i), input_tensor, 3, 3, input_feature_num, 16, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)                
            
        # conv    
        i = i + 1        
        out1 = self.build_depthwise_separable_conv("CNN%d" % (i), out1, 3, 3, 16, 16, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)   
               
        # edge synthesis block
        # M = 2
        out5, i = self.edge_synth_block_type1(out1, i, edge_layers=2, inp_ch=16, out_ch_middle=16, out_ch_final=16, normal_conv_branch=1)
                       
        # concat
        out10 = tf.concat((out1, out5), 3, name="feature_concat") 
        
        # more edge synthesis blocks
        num_esb = 2
        inp_ch = 32
        for j in range(num_esb):
            # conv dep sep
            i = i + 1
    
            # edge synthesis block
            if j < (num_esb - 1):
                out7 = self.build_depthwise_separable_conv("CNN%d" % (i), out10, 3, 3, 32, 16, use_bias=True, activator=self.activator,
                                    use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)             
                out9, i = self.edge_synth_block_type1(out7, i, edge_layers=1, inp_ch=16, out_ch_middle=16, out_ch_final=16, normal_conv_branch=1)
            else:
                # last block
                out7 = self.build_depthwise_separable_conv("CNN%d" % (i), out10, 3, 3, 32, 16, use_bias=True, activator=self.activator,
                                    use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)                 
                out9, i = self.edge_synth_block_type1(out7, i, edge_layers=1, inp_ch=16, out_ch_middle=16, out_ch_final=32, normal_conv_branch=1)
                inp_ch = 48
        
            # concat
            out10 = tf.concat((out7, out9), 3, name="feature_concat")                       
        
        # concat features from 1st esb
        #inp_ch += 16
        #out10 = tf.concat((out10, out5), 3, name="feature_concat")
        
        # dimension reduction
        # [1x1x24x16]  
        out_ch_num = 48   
        if self.scale == 3:        
            out_ch_num = 45
        i = i + 1
        out11 = self.build_depthwise_separable_conv("CNN%d" % (i), out10, 3, 3, inp_ch, out_ch_num, use_bias=True, activator=self.activator,
                                    use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)         
                                                  
        # building upsampling layer
        if self.scale == 1:
            # for AR network
            out12 = out11
        else:
            # for SR network        
            out12 = tf.depth_to_space(out11, self.scale)
        #update input pixels after calling depth to space
        self.pix_per_input = self.scale
        
        # compute the channels appropriately based on scale and depth2space        
        inp_ch_num = out_ch_num // (self.scale * self.scale)        
                               
        # [3x3x16x8]
        i = i + 1
        out11 = self.build_conv("CNN%d" % (i), out12, 3, 3, inp_ch_num, 1, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)  

        # global residual
        self.y_ = tf.add(self.H[-1], self.x2, name="output")

        if self.save_weights:
            with tf.name_scope("Y_"):
                util.add_summaries("output", self.name, self.y_, save_stddev=True, save_mean=True)	        

    '''
    # Separate branches for horz, vert, horz+vert synthesis blocks
    '''
    def build_graph_v5_3_edge_concat(self):

        self.x = tf.placeholder(tf.float32, shape=[None, None, None, self.channels], name="x")
        self.y = tf.placeholder(tf.float32, shape=[None, None, None, self.output_channels], name="y")
        self.x2 = tf.placeholder(tf.float32, shape=[None, None, None, self.output_channels], name="x2")
        self.dropout = tf.placeholder(tf.float32, shape=[], name="dropout_keep_rate")
        self.is_training = tf.placeholder(tf.bool, name="is_training")

        # building feature extraction layers

        output_feature_num = self.filters
        total_output_feature_num = 0
        input_feature_num = self.channels
        input_tensor = self.x
		
        # custom architecture
        i = 0	

        if self.save_weights:
            with tf.name_scope("X"):
                util.add_summaries("output", self.name, self.x, save_stddev=True, save_mean=True)

        # conv    
        i = i + 1        
        out_1 = self.build_conv("CNN%d" % (i), input_tensor, 3, 3, input_feature_num, 16, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)                
        # conv    
        i = i + 1        
        out_11 = self.build_depthwise_separable_conv("CNN%d" % (i), out_1, 3, 3, 16, 16, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate) 
                               
        # conv atrous   
        i = i + 1        
        out_2 = self.build_conv_atrous("CNN%d" % (i), input_tensor, 3, 3, input_feature_num, 16, use_bias=True, activator=self.activator,
                            use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate, dilate_stride=2)
        # conv atrous   
        i = i + 1        
        out_21 = self.build_depthwise_separable_conv("CNN%d" % (i), out_2, 3, 3, 16, 16, use_bias=True, activator=self.activator,
                            use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)
                            
        # conv atrous   
        i = i + 1        
        out_4 = self.build_conv_atrous("CNN%d" % (i), input_tensor, 3, 3, input_feature_num, 16, use_bias=True, activator=self.activator,
                            use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate, dilate_stride=4)
        # conv atrous   
        i = i + 1        
        out_41 = self.build_depthwise_separable_conv("CNN%d" % (i), out_4, 3, 3, 16, 16, use_bias=True, activator=self.activator,
                            use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)
                            
        # conv atrous   
        i = i + 1        
        out_8 = self.build_conv_atrous("CNN%d" % (i), input_tensor, 3, 3, input_feature_num, 16, use_bias=True, activator=self.activator,
                            use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate, dilate_stride=8)
 
        # conv atrous   
        i = i + 1        
        out_81 = self.build_depthwise_separable_conv("CNN%d" % (i), out_8, 3, 3, 16, 16, use_bias=True, activator=self.activator,
                            use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)
                                    
        # concat
        out_12 = tf.concat((out_11, out_21), 3, name="feature_concat") 
        out_48 = tf.concat((out_41, out_81), 3, name="feature_concat")

        # conv dep-sep
        i = i + 1
        out_100 = self.build_depthwise_separable_conv("CNN%d" % (i), out_12, 3, 3, 32, 16, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)  
        # conv atrous
        i = i + 1
        out_101 = self.build_conv_atrous("CNN%d" % (i), out_100, 3, 3, 16, 16, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate, dilate_stride=2) 
                               
        # conv dep-sep
        i = i + 1
        out_200 = self.build_depthwise_separable_conv("CNN%d" % (i), out_48, 3, 3, 32, 16, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)         
        # conv atrous                               
        i = i + 1
        out_201 = self.build_conv_atrous("CNN%d" % (i), out_200, 3, 3, 16, 16, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate, dilate_stride=4)  

        # concat
        out3 = tf.concat((out_101, out_201), 3, name="feature_concat")

        # conv dep-sep
        i = i + 1
        out_300 = self.build_conv("CNN%d" % (i), out3, 3, 3, 32, 16, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)  
                               
        # conv atrous
        i = i + 1
        out_401 = self.build_conv("CNN%d" % (i), out_300, 3, 3, 16, 8, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)         
        # conv atrous
        i = i + 1
        out_402 = self.build_conv("CNN%d" % (i), out_401, 3, 3, 8, 8, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)   
                               
        # conv atrous
        i = i + 1
        out_501 = self.build_conv_atrous("CNN%d" % (i), out_300, 3, 3, 16, 8, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate, dilate_stride=2) 
        # conv atrous
        i = i + 1
        out_502 = self.build_conv("CNN%d" % (i), out_501, 3, 3, 8, 8, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)  
                               
        # concat
        out5 = tf.concat((out_402, out_502), 3, name="feature_concat") 
        
        # conv dep-sep
        i = i + 1
        out_500 = self.build_depthwise_separable_conv("CNN%d" % (i), out5, 3, 3, 16, 16, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)        
        
        # concat
        out10 = tf.concat((out_300, out_500), 3, name="feature_concat") 
        
        # dimension reduction
        # [1x1x24x16]  
        out_ch_num = 32    
        i = i + 1
        out11 = self.build_depthwise_separable_conv("CNN%d" % (i), out10, 3, 3, 32, out_ch_num, use_bias=True, activator=self.activator,
                                    use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)                      
        
        # building upsampling layer
        if self.scale == 1:
            # for AR network
            out12 = out11
        else:
            # for SR network        
            out12 = tf.depth_to_space(out11, self.scale)
        #update input pixels after calling depth to space
        self.pix_per_input = self.scale
        
        # compute the channels appropriately based on scale and depth2space        
        inp_ch_num = out_ch_num // (self.scale * self.scale)        
                               
        # [3x3x16x8]
        i = i + 1
        out11 = self.build_conv("CNN%d" % (i), out12, 3, 3, inp_ch_num, 1, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)  

        # global residual
        self.y_ = tf.add(self.H[-1], self.x2, name="output")

        if self.save_weights:
            with tf.name_scope("Y_"):
                util.add_summaries("output", self.name, self.y_, save_stddev=True, save_mean=True)	        
                

    '''
    # Atrous convolutions to reduce Artifacts across 8x8 blocks
    '''
    def build_graph_v5_car(self):

        self.x = tf.placeholder(tf.float32, shape=[None, None, None, self.channels], name="x")
        self.y = tf.placeholder(tf.float32, shape=[None, None, None, self.output_channels], name="y")
        self.x2 = tf.placeholder(tf.float32, shape=[None, None, None, self.output_channels], name="x2")
        self.dropout = tf.placeholder(tf.float32, shape=[], name="dropout_keep_rate")
        self.is_training = tf.placeholder(tf.bool, name="is_training")

        # building feature extraction layers

        output_feature_num = self.filters
        total_output_feature_num = 0
        input_feature_num = self.channels
        input_tensor = self.x
		
        # custom architecture
        i = 0	

        if self.save_weights:
            with tf.name_scope("X"):
                util.add_summaries("output", self.name, self.x, save_stddev=True, save_mean=True)

        # conv    
        i = i + 1        
        out_1 = self.build_conv("CNN%d" % (i), input_tensor, 3, 3, input_feature_num, 16, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)                
        # conv    
        i = i + 1        
        out_1_5x5 = self.build_conv("CNN%d" % (i), input_tensor, 5, 5, input_feature_num, 16, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)                
                               
        # conv atrous   
        i = i + 1        
        out_2 = self.build_conv_atrous("CNN%d" % (i), input_tensor, 3, 3, input_feature_num, 16, use_bias=True, activator=self.activator,
                            use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate, dilate_stride=2)
        # conv atrous   
        i = i + 1        
        out_2_5x5 = self.build_conv_atrous("CNN%d" % (i), input_tensor, 5, 5, input_feature_num, 16, use_bias=True, activator=self.activator,
                            use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate, dilate_stride=2)
                            
        # conv atrous   
        i = i + 1        
        out_4 = self.build_conv_atrous("CNN%d" % (i), input_tensor, 3, 3, input_feature_num, 16, use_bias=True, activator=self.activator,
                            use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate, dilate_stride=4)
        
        # conv atrous   
        i = i + 1        
        out_8 = self.build_conv_atrous("CNN%d" % (i), input_tensor, 3, 3, input_feature_num, 16, use_bias=True, activator=self.activator,
                            use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate, dilate_stride=8)
                                    
        # concat
        out_1_1 = tf.concat((out_1, out_1_5x5), 3, name="feature_concat") 
        out_2_1 = tf.concat((out_2, out_2_5x5), 3, name="feature_concat") 
        out_48 = tf.concat((out_4, out_8), 3, name="feature_concat")

        # conv dep-sep
        i = i + 1
        out_100 = self.build_depthwise_separable_conv("CNN%d" % (i), out_1_1, 3, 3, 32, 16, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)                                 
        # spatial attention   
        i = i + 1        
        out_100_1 = self.spatial_attention("CNN%d" % (i), out_100, 1, 1, 16, 16, use_bias=True, activator=self.activator)                               
        # conv atrous
        i = i + 1
        out_101 = self.build_conv("CNN%d" % (i), out_100_1, 3, 3, 16, 16, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate) 

        # conv dep-sep
        i = i + 1
        out_200 = self.build_depthwise_separable_conv("CNN%d" % (i), out_2_1, 3, 3, 32, 16, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)                                 
        # spatial attention   
        i = i + 1        
        out_200_1 = self.spatial_attention("CNN%d" % (i), out_200, 1, 1, 16, 16, use_bias=True, activator=self.activator)                               
        # conv atrous
        i = i + 1
        out_201 = self.build_conv_atrous("CNN%d" % (i), out_200_1, 3, 3, 16, 16, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate, dilate_stride=2) 
                               
        # conv dep-sep
        i = i + 1
        out_48_1 = self.build_depthwise_separable_conv("CNN%d" % (i), out_48, 3, 3, 32, 16, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)   
        # spatial attention   
        i = i + 1        
        out_48_2 = self.spatial_attention("CNN%d" % (i), out_48_1, 1, 1, 16, 16, use_bias=True, activator=self.activator)                               
        # conv atrous                               
        i = i + 1
        out_48_3 = self.build_conv_atrous("CNN%d" % (i), out_48_2, 3, 3, 16, 16, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate, dilate_stride=4)  

        # concat
        out3 = tf.concat((out_201, out_48_3), 3, name="feature_concat")
        # conv dep-sep     
        i = i + 1
        out_ch_num = 16
        out4 = self.build_depthwise_separable_conv("CNN%d" % (i), out3, 3, 3, 32, out_ch_num, use_bias=True, activator=self.activator,
                                    use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)          
        # spatial attention   
        i = i + 1        
        out5 = self.spatial_attention("CNN%d" % (i), out4, 1, 1, out_ch_num, out_ch_num, use_bias=True, activator=self.activator) 
        
        # concat
        out6 = tf.concat((out_101, out5), 3, name="feature_concat")
        
        # conv dep-sep 
        out_ch_num = 32    
        i = i + 1
        out10 = self.build_depthwise_separable_conv("CNN%d" % (i), out6, 3, 3, 32, out_ch_num, use_bias=True, activator=self.activator,
                                    use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)                                    
        
        # building upsampling layer
        if self.scale == 1:
            # for AR network
            out12 = out10
        else:
            # for SR network        
            out12 = tf.depth_to_space(out10, self.scale)
        #update input pixels after calling depth to space
        self.pix_per_input = self.scale
        
        # compute the channels appropriately based on scale and depth2space        
        inp_ch_num = out_ch_num // (self.scale * self.scale)        
                               
        # conv
        i = i + 1
        out13 = self.build_conv("CNN%d" % (i), out12, 3, 3, inp_ch_num, 1, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)  

        # global residual
        self.y_ = tf.add(self.H[-1], self.x2, name="output")

        if self.save_weights:
            with tf.name_scope("Y_"):
                util.add_summaries("output", self.name, self.y_, save_stddev=True, save_mean=True)	        
                
    '''
    # Atrous convolutions to reduce Artifacts across 8x8 blocks
    '''
    def build_graph_v5_4_edge_concat(self):

        self.x = tf.placeholder(tf.float32, shape=[None, None, None, self.channels], name="x")
        self.y = tf.placeholder(tf.float32, shape=[None, None, None, self.output_channels], name="y")
        self.x2 = tf.placeholder(tf.float32, shape=[None, None, None, self.output_channels], name="x2")
        self.dropout = tf.placeholder(tf.float32, shape=[], name="dropout_keep_rate")
        self.is_training = tf.placeholder(tf.bool, name="is_training")

        # building feature extraction layers

        output_feature_num = self.filters
        total_output_feature_num = 0
        input_feature_num = self.channels
        input_tensor = self.x
		
        # custom architecture
        i = 0	

        if self.save_weights:
            with tf.name_scope("X"):
                util.add_summaries("output", self.name, self.x, save_stddev=True, save_mean=True)

        # conv    
        i = i + 1        
        out_1 = self.build_conv("CNN%d" % (i), input_tensor, 3, 3, input_feature_num, 16, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)                
        # conv    
        i = i + 1        
        out_11 = self.build_conv("CNN%d" % (i), out_1, 3, 3, 16, 16, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate) 
                               
        # conv atrous   
        i = i + 1        
        out_2 = self.build_conv_atrous("CNN%d" % (i), input_tensor, 3, 3, input_feature_num, 16, use_bias=True, activator=self.activator,
                            use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate, dilate_stride=2)
                            
        # conv atrous   
        i = i + 1        
        out_4 = self.build_conv_atrous("CNN%d" % (i), input_tensor, 3, 3, input_feature_num, 16, use_bias=True, activator=self.activator,
                            use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate, dilate_stride=4)
        
        # conv atrous   
        i = i + 1        
        out_8 = self.build_conv_atrous("CNN%d" % (i), input_tensor, 3, 3, input_feature_num, 16, use_bias=True, activator=self.activator,
                            use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate, dilate_stride=8)
                                    
        # concat
        out_12 = tf.concat((out_11, out_2), 3, name="feature_concat") 
        out_48 = tf.concat((out_4, out_8), 3, name="feature_concat")

        # conv dep-sep
        i = i + 1
        out_100 = self.build_depthwise_separable_conv("CNN%d" % (i), out_12, 3, 3, 32, 16, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)  
        # conv atrous
        i = i + 1
        out_101 = self.build_conv_atrous("CNN%d" % (i), out_100, 3, 3, 16, 8, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate, dilate_stride=2) 
                               
        # conv dep-sep
        i = i + 1
        out_200 = self.build_depthwise_separable_conv("CNN%d" % (i), out_48, 3, 3, 32, 16, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)         
        # conv atrous                               
        i = i + 1
        out_201 = self.build_conv_atrous("CNN%d" % (i), out_200, 3, 3, 16, 8, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate, dilate_stride=4)  

        # concat
        out3 = tf.concat((out_101, out_201), 3, name="feature_concat")

        # conv dep-sep
        i = i + 1
        out_300 = self.build_conv("CNN%d" % (i), out3, 3, 3, 16, 16, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)  
        # residual
        #out_301 = out_300 + out_1
        out_301 = tf.concat((out_300, out_11), 3, name="feature_concat")
        
        # conv dep-sep
        i = i + 1
        out_400 = self.build_depthwise_separable_conv("CNN%d" % (i), out_301, 3, 3, 32, 16, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate) 
                               
        # conv atrous
        i = i + 1
        out_401 = self.build_conv("CNN%d" % (i), out_400, 3, 3, 16, 8, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)         
             
        # conv atrous
        i = i + 1
        out_402 = self.build_conv_atrous("CNN%d" % (i), out_400, 3, 3, 16, 8, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate, dilate_stride=2) 

        # concat
        out5 = tf.concat((out_401, out_402), 3, name="feature_concat") 
        
        # conv dep-sep
        i = i + 1
        out_500 = self.build_depthwise_separable_conv("CNN%d" % (i), out5, 3, 3, 16, 16, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)        
        
        # concat
        out10 = tf.concat((out_300, out_500), 3, name="feature_concat") 
        
        # dimension reduction
        # [1x1x24x16]  
        out_ch_num = 32    
        i = i + 1
        out11 = self.build_depthwise_separable_conv("CNN%d" % (i), out10, 3, 3, 32, out_ch_num, use_bias=True, activator=self.activator,
                                    use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)                      
        
        # building upsampling layer
        if self.scale == 1:
            # for AR network
            out12 = out11
        else:
            # for SR network        
            out12 = tf.depth_to_space(out11, self.scale)
        #update input pixels after calling depth to space
        self.pix_per_input = self.scale
        
        # compute the channels appropriately based on scale and depth2space        
        inp_ch_num = out_ch_num // (self.scale * self.scale)        
                               
        # [3x3x16x8]
        i = i + 1
        out11 = self.build_conv("CNN%d" % (i), out12, 3, 3, inp_ch_num, 1, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)  

        # global residual
        self.y_ = tf.add(self.H[-1], self.x2, name="output")

        if self.save_weights:
            with tf.name_scope("Y_"):
                util.add_summaries("output", self.name, self.y_, save_stddev=True, save_mean=True)	        
 
 

    '''
    # Similar to v3 and inspired from v5
    '''
    def build_graph_v6_edge_concat(self):
        self.x = tf.placeholder(tf.float32, shape=[None, None, None, self.channels], name="x")
        self.y = tf.placeholder(tf.float32, shape=[None, None, None, self.output_channels], name="y")
        self.x2 = tf.placeholder(tf.float32, shape=[None, None, None, self.output_channels], name="x2")
        self.dropout = tf.placeholder(tf.float32, shape=[], name="dropout_keep_rate")
        self.is_training = tf.placeholder(tf.bool, name="is_training")

        # building feature extraction layers

        output_feature_num = self.filters
        total_output_feature_num = 0
        input_feature_num = self.channels
        input_tensor = self.x
		
        # custom architecture
        i = 0	

        if self.save_weights:
            with tf.name_scope("X"):
                util.add_summaries("output", self.name, self.x, save_stddev=True, save_mean=True)

        # conv    
        i = i + 1        
        out1 = self.build_conv("CNN%d" % (i), input_tensor, 3, 3, input_feature_num, 16, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)                

        # conv dep-sep  
        i = i + 1
        out100 = self.build_depthwise_separable_conv("CNN%d" % (i), out1, 3, 3, 16, 8, use_bias=True, activator=self.activator,
                                    use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate) 
                                    
        # conv     
        i = i + 1
        out2 = self.build_conv("CNN%d" % (i), out100, 3, 3, 8, 4, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)                               

        # conv     
        i = i + 1
        out3 = self.build_conv("CNN%d" % (i), out100, 3, 3, 8, 4, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate) 
                                                       
        # concat
        out4 = tf.concat((out2, out3), 3, name="feature_concat")                                                                   
                  
        # conv dep-sep      
        i = i + 1
        out5 = self.build_depthwise_separable_conv("CNN%d" % (i), out4, 3, 3, 8, 8, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)  
                       
        # concat
        out6 = tf.concat((out100, out5), 3, name="feature_concat")        
       
        # conv dep-sep      
        i = i + 1
        out200 = self.build_depthwise_separable_conv("CNN%d" % (i), out6, 3, 3, 16, 8, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)  
                               
        # conv dep-sep      
        i = i + 1
        out7 = self.build_depthwise_separable_conv("CNN%d" % (i), out200, 3, 3, 8, 8, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate) 
                               
        # conv dep-sep       
        i = i + 1
        out8 = self.build_depthwise_separable_conv("CNN%d" % (i), out200, 3, 3, 8, 8, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)                           
         
        # concat
        out10 = tf.concat((out6, out7, out8), 3, name="feature_concat")                      
                               
        # conv dep-sep
        out_ch_num = 32    
        i = i + 1
        out11 = self.build_depthwise_separable_conv("CNN%d" % (i), out10, 3, 3, 32, out_ch_num, use_bias=True, activator=self.activator,
                                    use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)         
                                                  
        # building upsampling layer
        if self.scale == 1:
            # for AR network
            out12 = out11
        else:
            # for SR network        
            out12 = tf.depth_to_space(out11, self.scale)
        #update input pixels after calling depth to space
        self.pix_per_input = self.scale
        
        # compute the channels appropriately based on scale and depth2space        
        inp_ch_num = out_ch_num // (self.scale * self.scale)
        # [3x3x16x8]
        i = i + 1
        out11 = self.build_conv("CNN%d" % (i), out12, 3, 3, inp_ch_num, 1, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)  

        # global residual
        self.y_ = tf.add(self.H[-1], self.x2, name="output")

        if self.save_weights:
            with tf.name_scope("Y_"):
                util.add_summaries("output", self.name, self.y_, save_stddev=True, save_mean=True)	        

    '''
    # similar to v6 but low complex than v6
    '''
    def build_graph_v6_1_edge_concat(self):
        self.x = tf.placeholder(tf.float32, shape=[None, None, None, self.channels], name="x")
        self.y = tf.placeholder(tf.float32, shape=[None, None, None, self.output_channels], name="y")
        self.x2 = tf.placeholder(tf.float32, shape=[None, None, None, self.output_channels], name="x2")
        self.dropout = tf.placeholder(tf.float32, shape=[], name="dropout_keep_rate")
        self.is_training = tf.placeholder(tf.bool, name="is_training")

        # building feature extraction layers

        output_feature_num = self.filters
        total_output_feature_num = 0
        input_feature_num = self.channels
        input_tensor = self.x
		
        # custom architecture
        i = 0	

        if self.save_weights:
            with tf.name_scope("X"):
                util.add_summaries("output", self.name, self.x, save_stddev=True, save_mean=True)

        # conv    
        i = i + 1        
        out1 = self.build_conv("CNN%d" % (i), input_tensor, 3, 3, input_feature_num, 16, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)                

        # conv dep-sep  
        i = i + 1
        out100 = self.build_depthwise_separable_conv("CNN%d" % (i), out1, 3, 3, 16, 8, use_bias=True, activator=self.activator,
                                    use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate) 
                                    
        # conv     
        i = i + 1
        out2 = self.build_conv("CNN%d" % (i), out100, 1, 3, 8, 8, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)                               

        # conv     
        i = i + 1
        out3 = self.build_conv("CNN%d" % (i), out100, 3, 1, 8, 8, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate) 
                                                       
        # concat
        out4 = tf.concat((out2, out3), 3, name="feature_concat")                                                                   
                  
        # conv dep-sep      
        i = i + 1
        out200 = self.build_depthwise_separable_conv("CNN%d" % (i), out4, 3, 3, 16, 8, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)  
                                                     
        # conv dep-sep      
        i = i + 1
        out7 = self.build_conv("CNN%d" % (i), out200, 1, 3, 8, 4, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate) 
                               
        # conv dep-sep       
        i = i + 1
        out8 = self.build_conv("CNN%d" % (i), out200, 3, 1, 8, 4, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)                           
         
        # concat
        out10 = tf.concat((out7, out8), 3, name="feature_concat")         

        # conv dep-sep      
        i = i + 1
        out300 = self.build_depthwise_separable_conv("CNN%d" % (i), out10, 3, 3, 8, 8, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)        
        
        # concat
        out23 = tf.concat((out200, out300), 3, name="feature_concat")   
        
        # conv dep-sep
        out_ch_num = 16   
        if self.scale == 4:
            # slightly high complexity for 4x, check any improvement?
            out_ch_num = 16#32
        i = i + 1
        out11 = self.build_depthwise_separable_conv("CNN%d" % (i), out23, 3, 3, 16, out_ch_num, use_bias=True, activator=self.activator,
                                    use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)         
                                                  
        # building upsampling layer
        if self.scale == 1:
            # for AR network
            out12 = out11
        else:
            # for SR network        
            out12 = tf.depth_to_space(out11, self.scale)
        #update input pixels after calling depth to space
        self.pix_per_input = self.scale
        
        # compute the channels appropriately based on scale and depth2space        
        inp_ch_num = out_ch_num // (self.scale * self.scale)
        # [3x3x16x8]
        i = i + 1
        out11 = self.build_conv("CNN%d" % (i), out12, 3, 3, inp_ch_num, 1, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)  

        # global residual
        self.y_ = tf.add(self.H[-1], self.x2, name="output")
        #self.y_ = tf.round(self.y_, name="round")

        if self.save_weights:
            with tf.name_scope("Y_"):
                util.add_summaries("output", self.name, self.y_, save_stddev=True, save_mean=True)	        

    '''
    # similar to v6 but low complex than v6
    '''
    def build_graph_v6_2_edge_concat(self):
        self.x = tf.placeholder(tf.float32, shape=[None, None, None, self.channels], name="x")
        self.y = tf.placeholder(tf.float32, shape=[None, None, None, self.output_channels], name="y")
        self.x2 = tf.placeholder(tf.float32, shape=[None, None, None, self.output_channels], name="x2")
        self.dropout = tf.placeholder(tf.float32, shape=[], name="dropout_keep_rate")
        self.is_training = tf.placeholder(tf.bool, name="is_training")

        # building feature extraction layers

        output_feature_num = self.filters
        total_output_feature_num = 0
        input_feature_num = self.channels
        input_tensor = self.x
		
        # custom architecture
        i = 0	

        if self.save_weights:
            with tf.name_scope("X"):
                util.add_summaries("output", self.name, self.x, save_stddev=True, save_mean=True)

        # conv    
        i = i + 1        
        out1 = self.build_conv("CNN%d" % (i), input_tensor, 3, 3, input_feature_num, 16, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)                

        # conv dep-sep  
        i = i + 1
        out100 = self.build_depthwise_separable_conv("CNN%d" % (i), out1, 3, 3, 16, 8, use_bias=True, activator=self.activator,
                                    use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate) 
                                    
        # conv     
        i = i + 1
        out102 = self.build_conv("CNN%d" % (i), out100, 3, 3, 8, 8, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)                                     
  
        # conv     
        i = i + 1
        out2 = self.build_conv("CNN%d" % (i), out102, 1, 3, 8, 4, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)                               

        # conv     
        i = i + 1
        out3 = self.build_conv("CNN%d" % (i), out102, 3, 1, 8, 4, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate) 
                                                       
        # concat
        out4 = tf.concat((out2, out3), 3, name="feature_concat")    

        # conv dep-sep      
        i = i + 1
        out200 = self.build_conv("CNN%d" % (i), out4, 3, 3, 8, 8, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)          

        # concat
        out4 = tf.concat((out102, out200), 3, name="feature_concat")                                     
        
        # conv dep-sep      
        i = i + 1
        out201 = self.build_depthwise_separable_conv("CNN%d" % (i), out4, 3, 3, 16, 8, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)          

        i = i + 1
        out202 = self.build_depthwise_separable_conv("CNN%d" % (i), out4, 3, 3, 16, 8, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)  
                               
        # concat
        out4 = tf.concat((out201, out202), 3, name="feature_concat")              
        
        
        # conv dep-sep
        out_ch_num = 16   
        i = i + 1
        out11 = self.build_depthwise_separable_conv("CNN%d" % (i), out4, 3, 3, 16, out_ch_num, use_bias=True, activator=self.activator,
                                    use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)         
                                                  
        # building upsampling layer
        if self.scale == 1:
            # for AR network
            out12 = out11
        else:
            # for SR network        
            out12 = tf.depth_to_space(out11, self.scale)
        #update input pixels after calling depth to space
        self.pix_per_input = self.scale
        
        # compute the channels appropriately based on scale and depth2space        
        inp_ch_num = out_ch_num // (self.scale * self.scale)
        # [3x3x16x8]
        i = i + 1
        out11 = self.build_conv("CNN%d" % (i), out12, 3, 3, inp_ch_num, 1, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)  

        # global residual
        self.y_ = tf.add(self.H[-1], self.x2, name="output")

        if self.save_weights:
            with tf.name_scope("Y_"):
                util.add_summaries("output", self.name, self.y_, save_stddev=True, save_mean=True)	        

    '''
    # similar to v6 but low complex than v6
    '''
    def build_graph_v6_3_edge_concat(self):
        self.x = tf.placeholder(tf.float32, shape=[None, None, None, self.channels], name="x")
        self.y = tf.placeholder(tf.float32, shape=[None, None, None, self.output_channels], name="y")
        self.x2 = tf.placeholder(tf.float32, shape=[None, None, None, self.output_channels], name="x2")
        self.dropout = tf.placeholder(tf.float32, shape=[], name="dropout_keep_rate")
        self.is_training = tf.placeholder(tf.bool, name="is_training")

        # building feature extraction layers

        output_feature_num = self.filters
        total_output_feature_num = 0
        input_feature_num = self.channels
        input_tensor = self.x
		
        # custom architecture
        i = 0	

        if self.save_weights:
            with tf.name_scope("X"):
                util.add_summaries("output", self.name, self.x, save_stddev=True, save_mean=True)

        # conv    
        i = i + 1        
        out1 = self.build_conv("CNN%d" % (i), input_tensor, 3, 3, input_feature_num, 16, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)                

        # conv dep-sep  
        i = i + 1
        out100 = self.build_depthwise_separable_conv("CNN%d" % (i), out1, 3, 3, 16, 8, use_bias=True, activator=self.activator,
                                    use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate) 
                                    
        # conv     
        i = i + 1
        out2 = self.build_conv("CNN%d" % (i), out100, 1, 3, 8, 4, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)                               

        # conv     
        i = i + 1
        out3 = self.build_conv("CNN%d" % (i), out100, 3, 1, 8, 4, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate) 
                                                       
        # concat
        out4 = tf.concat((out2, out3), 3, name="feature_concat")                                                                   
                  
        # conv dep-sep      
        i = i + 1
        out200 = self.build_depthwise_separable_conv("CNN%d" % (i), out4, 3, 3, 8, 8, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)  
                                                     
        # conv dep-sep      
        i = i + 1
        out7 = self.build_conv("CNN%d" % (i), out200, 1, 3, 8, 4, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate) 
                               
        # conv dep-sep       
        i = i + 1
        out8 = self.build_conv("CNN%d" % (i), out200, 3, 1, 8, 4, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)                           
         
        # concat
        out10 = tf.concat((out7, out8), 3, name="feature_concat")         

        # conv dep-sep      
        i = i + 1
        out300 = self.build_depthwise_separable_conv("CNN%d" % (i), out10, 3, 3, 8, 8, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)        
        
        # concat
        out23 = tf.concat((out200, out300), 3, name="feature_concat")   
        
        # conv dep-sep
        out_ch_num = 16   
        if self.scale == 4:
            # slightly high complexity for 4x, check any improvement?
            out_ch_num = 16#32
        i = i + 1
        out11 = self.build_depthwise_separable_conv("CNN%d" % (i), out23, 3, 3, 16, out_ch_num, use_bias=True, activator=self.activator,
                                    use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)         
                                                  
        # building upsampling layer
        if self.scale == 1:
            # for AR network
            out12 = out11
        else:
            # for SR network        
            out12 = tf.depth_to_space(out11, self.scale)
        #update input pixels after calling depth to space
        self.pix_per_input = self.scale
        
        # compute the channels appropriately based on scale and depth2space        
        inp_ch_num = out_ch_num // (self.scale * self.scale)
        # [3x3x16x8]
        i = i + 1
        out11 = self.build_conv("CNN%d" % (i), out12, 3, 3, inp_ch_num, 1, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)  

        # global residual
        self.y_ = tf.add(self.H[-1], self.x2, name="output")
        #self.y_ = tf.round(self.y_, name="round")

        if self.save_weights:
            with tf.name_scope("Y_"):
                util.add_summaries("output", self.name, self.y_, save_stddev=True, save_mean=True)	        

                
                
    '''
    # Very light
    '''
    def build_graph_v7_edge_concat(self):
        self.x = tf.placeholder(tf.float32, shape=[None, None, None, self.channels], name="x")
        self.y = tf.placeholder(tf.float32, shape=[None, None, None, self.output_channels], name="y")
        self.x2 = tf.placeholder(tf.float32, shape=[None, None, None, self.output_channels], name="x2")
        self.dropout = tf.placeholder(tf.float32, shape=[], name="dropout_keep_rate")
        self.is_training = tf.placeholder(tf.bool, name="is_training")

        # building feature extraction layers

        output_feature_num = self.filters
        total_output_feature_num = 0
        input_feature_num = self.channels
        input_tensor = self.x
		
        # custom architecture
        i = 0	

        if self.save_weights:
            with tf.name_scope("X"):
                util.add_summaries("output", self.name, self.x, save_stddev=True, save_mean=True)

        # conv    
        i = i + 1        
        out1 = self.build_conv("CNN%d" % (i), input_tensor, 3, 3, input_feature_num, 8, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)                

        # conv     
        i = i + 1
        out2 = self.build_conv("CNN%d" % (i), out1, 1, 3, 8, 4, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)                               

        # conv dep-sep      
        i = i + 1
        out2 = self.build_depthwise_separable_conv("CNN%d" % (i), out2, 3, 3, 4, 4, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)                                
                               
        # conv     
        i = i + 1
        out3 = self.build_conv("CNN%d" % (i), out1, 3, 1, 8, 4, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate) 
                         
        # conv dep-sep      
        i = i + 1
        out3 = self.build_depthwise_separable_conv("CNN%d" % (i), out3, 3, 3, 4, 4, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate) 
                               
        # concat
        out4 = tf.concat((out2, out3), 3, name="feature_concat")                                                                   
                 
        # conv  dep-sep   
        i = i + 1
        out200 = self.build_depthwise_separable_conv("CNN%d" % (i), out4, 3, 3, 8, 8, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)                   
                               
        # conv     
        i = i + 1
        out201 = self.build_conv("CNN%d" % (i), out200, 1, 3, 8, 4, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate) 
              
        # conv     
        i = i + 1
        out202 = self.build_conv("CNN%d" % (i), out200, 1, 3, 8, 4, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate) 
 
         # concat
        out4 = tf.concat((out4, out201, out202), 3, name="feature_concat")   
              
        # conv dep-sep
        out_ch_num = 8    
        i = i + 1
        out5 = self.build_depthwise_separable_conv("CNN%d" % (i), out4, 3, 3, 16, out_ch_num, use_bias=True, activator=self.activator,
                                    use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)         
                                                  
        # building upsampling layer
        if self.scale == 1:
            # for AR network
            out6 = out5
        else:
            # for SR network        
            out6 = tf.depth_to_space(out5, self.scale)
        #update input pixels after calling depth to space
        self.pix_per_input = self.scale
        
        # compute the channels appropriately based on scale and depth2space        
        inp_ch_num = out_ch_num // (self.scale * self.scale)        
        
        # [3x3x16x8]
        i = i + 1
        out7 = self.build_conv("CNN%d" % (i), out6, 3, 3, inp_ch_num, 1, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)  

        # global residual
        self.y_ = tf.add(self.H[-1], self.x2, name="output")

        if self.save_weights:
            with tf.name_scope("Y_"):
                util.add_summaries("output", self.name, self.y_, save_stddev=True, save_mean=True)	        

    '''
    # Very light
    '''
    def build_graph_v7_1_edge_concat(self):
        self.x = tf.placeholder(tf.float32, shape=[None, None, None, self.channels], name="x")
        self.y = tf.placeholder(tf.float32, shape=[None, None, None, self.output_channels], name="y")
        self.x2 = tf.placeholder(tf.float32, shape=[None, None, None, self.output_channels], name="x2")
        self.dropout = tf.placeholder(tf.float32, shape=[], name="dropout_keep_rate")
        self.is_training = tf.placeholder(tf.bool, name="is_training")

        # building feature extraction layers

        output_feature_num = self.filters
        total_output_feature_num = 0
        input_feature_num = self.channels
        input_tensor = self.x
		
        # custom architecture
        i = 0	

        if self.save_weights:
            with tf.name_scope("X"):
                util.add_summaries("output", self.name, self.x, save_stddev=True, save_mean=True)

        # conv    
        i = i + 1        
        out0 = self.build_conv("CNN%d" % (i), input_tensor, 3, 3, input_feature_num, 8, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)                

        # conv dep-sep      
        i = i + 1
        out1 = self.build_depthwise_separable_conv("CNN%d" % (i), out0, 3, 3, 8, 8, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)   
                               
        # conv     
        i = i + 1
        out2 = self.build_conv("CNN%d" % (i), out1, 1, 3, 8, 4, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)                               

        # conv dep-sep      
        i = i + 1
        out2 = self.build_depthwise_separable_conv("CNN%d" % (i), out2, 3, 3, 4, 4, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)                                
                               
        # conv     
        i = i + 1
        out3 = self.build_conv("CNN%d" % (i), out1, 3, 1, 8, 4, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate) 
                         
        # conv dep-sep      
        i = i + 1
        out3 = self.build_depthwise_separable_conv("CNN%d" % (i), out3, 3, 3, 4, 4, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate) 
                               
        # concat
        out4 = tf.concat((out2, out3), 3, name="feature_concat")                                                                   
                 
        # conv  dep-sep   
        i = i + 1
        out200 = self.build_depthwise_separable_conv("CNN%d" % (i), out4, 3, 3, 8, 8, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)                   
                               
        # conv     
        i = i + 1
        out201 = self.build_conv("CNN%d" % (i), out200, 1, 3, 8, 4, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate) 
              
        # conv     
        i = i + 1
        out202 = self.build_conv("CNN%d" % (i), out200, 1, 3, 8, 4, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate) 
 
         # concat
        out4 = tf.concat((out4, out201, out202), 3, name="feature_concat")    
              
        # conv dep-sep
        out_ch_num = 8    
        i = i + 1
        out5 = self.build_depthwise_separable_conv("CNN%d" % (i), out4, 3, 3, 16, out_ch_num, use_bias=True, activator=self.activator,
                                    use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)         
                                                  
        # building upsampling layer
        if self.scale == 1:
            # for AR network
            out6 = out5
        else:
            # for SR network        
            out6 = tf.depth_to_space(out5, self.scale)
        #update input pixels after calling depth to space
        self.pix_per_input = self.scale
        
        # compute the channels appropriately based on scale and depth2space        
        inp_ch_num = out_ch_num // (self.scale * self.scale)        
        
        # [3x3x16x8]
        i = i + 1
        out7 = self.build_conv("CNN%d" % (i), out6, 3, 3, inp_ch_num, 1, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)  

        # global residual
        self.y_ = tf.add(self.H[-1], self.x2, name="output")

        if self.save_weights:
            with tf.name_scope("Y_"):
                util.add_summaries("output", self.name, self.y_, save_stddev=True, save_mean=True)	        
                

    '''
    # Very light
    '''
    def build_graph_v8_edge_concat(self):
        self.x = tf.placeholder(tf.float32, shape=[None, None, None, self.channels], name="x")
        self.y = tf.placeholder(tf.float32, shape=[None, None, None, self.output_channels], name="y")
        self.x2 = tf.placeholder(tf.float32, shape=[None, None, None, self.output_channels], name="x2")
        self.dropout = tf.placeholder(tf.float32, shape=[], name="dropout_keep_rate")
        self.is_training = tf.placeholder(tf.bool, name="is_training")

        # building feature extraction layers

        output_feature_num = self.filters
        total_output_feature_num = 0
        input_feature_num = self.channels
        input_tensor = self.x
		
        # custom architecture
        i = 0	

        if self.save_weights:
            with tf.name_scope("X"):
                util.add_summaries("output", self.name, self.x, save_stddev=True, save_mean=True)

        # conv    
        i = i + 1        
        out1 = self.build_conv("CNN%d" % (i), input_tensor, 3, 3, input_feature_num, 8, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)                
                               
        # conv     
        i = i + 1
        out2 = self.build_conv("CNN%d" % (i), out1, 1, 3, 8, 4, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)                               

        # conv dep-sep      
        i = i + 1
        out2 = self.build_depthwise_separable_conv("CNN%d" % (i), out2, 3, 3, 4, 4, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)                                
                               
        # conv     
        i = i + 1
        out3 = self.build_conv("CNN%d" % (i), out1, 3, 1, 8, 4, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate) 
                         
        # conv dep-sep      
        i = i + 1
        out3 = self.build_depthwise_separable_conv("CNN%d" % (i), out3, 3, 3, 4, 4, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate) 
                               
        # concat
        out4 = tf.concat((out2, out3), 3, name="feature_concat")                                                                   
                  
                               
        # conv dep-sep
        out_ch_num = 8    
        i = i + 1
        out5 = self.build_depthwise_separable_conv("CNN%d" % (i), out4, 3, 3, 8, out_ch_num, use_bias=True, activator=self.activator,
                                    use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)         
                                                  
        # building upsampling layer
        if self.scale == 1:
            # for AR network
            out6 = out5
        else:
            # for SR network        
            out6 = tf.depth_to_space(out5, self.scale)
        #update input pixels after calling depth to space
        self.pix_per_input = self.scale
        
        # compute the channels appropriately based on scale and depth2space        
        inp_ch_num = out_ch_num // (self.scale * self.scale)
        # [3x3x16x8]
        i = i + 1
        out7 = self.build_conv("CNN%d" % (i), out6, 3, 3, inp_ch_num, 1, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)  

        # global residual
        self.y_ = tf.add(self.H[-1], self.x2, name="output")

        if self.save_weights:
            with tf.name_scope("Y_"):
                util.add_summaries("output", self.name, self.y_, save_stddev=True, save_mean=True)	        

    '''
    # Very light
    '''
    def build_graph_v8_1_edge_concat(self):
        self.x = tf.placeholder(tf.float32, shape=[None, None, None, self.channels], name="x")
        self.y = tf.placeholder(tf.float32, shape=[None, None, None, self.output_channels], name="y")
        self.x2 = tf.placeholder(tf.float32, shape=[None, None, None, self.output_channels], name="x2")
        self.dropout = tf.placeholder(tf.float32, shape=[], name="dropout_keep_rate")
        self.is_training = tf.placeholder(tf.bool, name="is_training")

        # building feature extraction layers

        output_feature_num = self.filters
        total_output_feature_num = 0
        input_feature_num = self.channels
        input_tensor = self.x
		
        # custom architecture
        i = 0	

        if self.save_weights:
            with tf.name_scope("X"):
                util.add_summaries("output", self.name, self.x, save_stddev=True, save_mean=True)

        # conv    
        i = i + 1        
        out0 = self.build_conv("CNN%d" % (i), input_tensor, 3, 3, input_feature_num, 8, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)                

        # conv dep-sep      
        i = i + 1
        out1 = self.build_depthwise_separable_conv("CNN%d" % (i), out0, 3, 3, 8, 8, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)   
                               
        # conv     
        i = i + 1
        out2 = self.build_conv("CNN%d" % (i), out1, 1, 3, 8, 4, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)                               

        # conv dep-sep      
        i = i + 1
        out2 = self.build_depthwise_separable_conv("CNN%d" % (i), out2, 3, 3, 4, 4, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)                                
                               
        # conv     
        i = i + 1
        out3 = self.build_conv("CNN%d" % (i), out1, 3, 1, 8, 4, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate) 
                         
        # conv dep-sep      
        i = i + 1
        out3 = self.build_depthwise_separable_conv("CNN%d" % (i), out3, 3, 3, 4, 4, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate) 
                               
        # concat
        out4 = tf.concat((out2, out3), 3, name="feature_concat")                                                                   
                  
                               
        # conv dep-sep
        out_ch_num = 8    
        i = i + 1
        out5 = self.build_depthwise_separable_conv("CNN%d" % (i), out4, 3, 3, 8, out_ch_num, use_bias=True, activator=self.activator,
                                    use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)         
                                                  
        # building upsampling layer
        if self.scale == 1:
            # for AR network
            out6 = out5
        else:
            # for SR network          
            out6 = tf.depth_to_space(out5, self.scale)
        #update input pixels after calling depth to space
        self.pix_per_input = self.scale
        
        # compute the channels appropriately based on scale and depth2space        
        inp_ch_num = out_ch_num // (self.scale * self.scale)
        # [3x3x16x8]
        i = i + 1
        out7 = self.build_conv("CNN%d" % (i), out6, 3, 3, inp_ch_num, 1, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)  

        # global residual
        self.y_ = tf.add(self.H[-1], self.x2, name="output")

        if self.save_weights:
            with tf.name_scope("Y_"):
                util.add_summaries("output", self.name, self.y_, save_stddev=True, save_mean=True)	        
                
                
    '''
    # Very light
    '''
    def build_graph_v9_edge_concat(self):
        self.x = tf.placeholder(tf.float32, shape=[None, None, None, self.channels], name="x")
        self.y = tf.placeholder(tf.float32, shape=[None, None, None, self.output_channels], name="y")
        self.x2 = tf.placeholder(tf.float32, shape=[None, None, None, self.output_channels], name="x2")
        self.dropout = tf.placeholder(tf.float32, shape=[], name="dropout_keep_rate")
        self.is_training = tf.placeholder(tf.bool, name="is_training")

        # building feature extraction layers

        output_feature_num = self.filters
        total_output_feature_num = 0
        input_feature_num = self.channels
        input_tensor = self.x
		
        # custom architecture
        i = 0	

        if self.save_weights:
            with tf.name_scope("X"):
                util.add_summaries("output", self.name, self.x, save_stddev=True, save_mean=True)

        # conv    
        i = i + 1        
        out1 = self.build_conv("CNN%d" % (i), input_tensor, 3, 3, input_feature_num, 8, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)                

        # conv     
        i = i + 1
        out2 = self.build_conv("CNN%d" % (i), out1, 1, 3, 8, 4, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)                               

        # conv dep-sep      
        i = i + 1
        out2 = self.build_depthwise_separable_conv("CNN%d" % (i), out2, 3, 3, 4, 4, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)                                
                               
        # conv     
        i = i + 1
        out3 = self.build_conv("CNN%d" % (i), out1, 3, 1, 8, 4, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate) 
                         
        # conv dep-sep      
        i = i + 1
        out3 = self.build_depthwise_separable_conv("CNN%d" % (i), out3, 3, 3, 4, 4, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate) 
                               
        # concat
        out4 = tf.concat((out2, out3), 3, name="feature_concat")                                                                   
                 
        # conv  dep-sep   
        i = i + 1
        out200 = self.build_depthwise_separable_conv("CNN%d" % (i), out4, 3, 3, 8, 8, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)                   
                               
        # concat
        out4 = tf.concat((out4, out200), 3, name="feature_concat")   
              
        # conv dep-sep
        out_ch_num = 8    
        i = i + 1
        out5 = self.build_depthwise_separable_conv("CNN%d" % (i), out4, 3, 3, 16, out_ch_num, use_bias=True, activator=self.activator,
                                    use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)         
                                                  
        # building upsampling layer
        if self.scale == 1:
            # for AR network
            out6 = out5
        else:
            # for SR network          
            out6 = tf.depth_to_space(out5, self.scale)
        #update input pixels after calling depth to space
        self.pix_per_input = self.scale
        
        # compute the channels appropriately based on scale and depth2space        
        inp_ch_num = out_ch_num // (self.scale * self.scale)        
        
        # [3x3x16x8]
        i = i + 1
        out7 = self.build_conv("CNN%d" % (i), out6, 3, 3, inp_ch_num, 1, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)  

        # global residual
        self.y_ = tf.add(self.H[-1], self.x2, name="output")

        if self.save_weights:
            with tf.name_scope("Y_"):
                util.add_summaries("output", self.name, self.y_, save_stddev=True, save_mean=True)	        

    '''
    # Very light
    '''
    def build_graph_v9_1_edge_concat(self):
        self.x = tf.placeholder(tf.float32, shape=[None, None, None, self.channels], name="x")
        self.y = tf.placeholder(tf.float32, shape=[None, None, None, self.output_channels], name="y")
        self.x2 = tf.placeholder(tf.float32, shape=[None, None, None, self.output_channels], name="x2")
        self.dropout = tf.placeholder(tf.float32, shape=[], name="dropout_keep_rate")
        self.is_training = tf.placeholder(tf.bool, name="is_training")

        # building feature extraction layers

        output_feature_num = self.filters
        total_output_feature_num = 0
        input_feature_num = self.channels
        input_tensor = self.x
		
        # custom architecture
        i = 0	

        if self.save_weights:
            with tf.name_scope("X"):
                util.add_summaries("output", self.name, self.x, save_stddev=True, save_mean=True)

        # conv    
        i = i + 1        
        out0 = self.build_conv("CNN%d" % (i), input_tensor, 3, 3, input_feature_num, 8, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)                

        # conv dep-sep      
        i = i + 1
        out1 = self.build_depthwise_separable_conv("CNN%d" % (i), out0, 3, 3, 8, 8, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate) 
                               
        # conv     
        i = i + 1
        out2 = self.build_conv("CNN%d" % (i), out1, 1, 3, 8, 4, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)                               

        # conv dep-sep      
        i = i + 1
        out2 = self.build_depthwise_separable_conv("CNN%d" % (i), out2, 3, 3, 4, 4, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)                                
                               
        # conv     
        i = i + 1
        out3 = self.build_conv("CNN%d" % (i), out1, 3, 1, 8, 4, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate) 
                         
        # conv dep-sep      
        i = i + 1
        out3 = self.build_depthwise_separable_conv("CNN%d" % (i), out3, 3, 3, 4, 4, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate) 
                               
        # concat
        out4 = tf.concat((out2, out3), 3, name="feature_concat")                                                                   
                 
        # conv  dep-sep   
        i = i + 1
        out200 = self.build_depthwise_separable_conv("CNN%d" % (i), out4, 3, 3, 8, 8, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)                   
                               
        # concat
        out4 = tf.concat((out4, out200), 3, name="feature_concat")   
              
        # conv dep-sep
        if self.scale == 2:
            out_ch_num = 8    
        elif self.scale == 4:
            out_ch_num = 32
        out_ch_num = 32
        i = i + 1
        out5 = self.build_depthwise_separable_conv("CNN%d" % (i), out4, 3, 3, 16, out_ch_num, use_bias=True, activator=self.activator,
                                    use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)         
                                                  
        # building upsampling layer
        if self.scale == 1:
            # for AR network
            out6 = out5
        else:
            # for SR network          
            out6 = tf.depth_to_space(out5, self.scale)
        #update input pixels after calling depth to space
        self.pix_per_input = self.scale
        
        # compute the channels appropriately based on scale and depth2space        
        inp_ch_num = out_ch_num // (self.scale * self.scale)        
        
        # [3x3x16x8]
        i = i + 1
        out7 = self.build_conv("CNN%d" % (i), out6, 3, 3, inp_ch_num, 1, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)  

        # global residual
        out8 = tf.add(self.H[-1], self.x2, name="output")

        # conv after residual
        i = i + 1
        self.y_ = self.build_conv("CNN%d" % (i), out8, 5, 5, 1, 1, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)  
                               
        if self.save_weights:
            with tf.name_scope("Y_"):
                util.add_summaries("output", self.name, self.y_, save_stddev=True, save_mean=True)	        
 
    '''
    # Arch suggested by Nitchith
    '''
    def build_graph_v33_edge_concat(self):
        self.x = tf.placeholder(tf.float32, shape=[None, None, None, self.channels], name="x")
        self.y = tf.placeholder(tf.float32, shape=[None, None, None, self.output_channels], name="y")
        self.x2 = tf.placeholder(tf.float32, shape=[None, None, None, self.output_channels], name="x2")
        self.dropout = tf.placeholder(tf.float32, shape=[], name="dropout_keep_rate")
        self.is_training = tf.placeholder(tf.bool, name="is_training")

        # building feature extraction layers

        output_feature_num = self.filters
        total_output_feature_num = 0
        input_feature_num = self.channels
        input_tensor = self.x
		
        # custom architecture
        i = 0	

        if self.save_weights:
            with tf.name_scope("X"):
                util.add_summaries("output", self.name, self.x, save_stddev=True, save_mean=True)

        # conv    
        i = i + 1        
        out0 = self.build_conv("CNN%d" % (i), input_tensor, 3, 3, input_feature_num, 8, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)                

        # conv dep-sep      
        i = i + 1
        out1 = self.build_depthwise_separable_conv("CNN%d" % (i), out0, 3, 3, 8, 16, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate) 
                               
        # conv dep-sep      
        out_ch_num = 16
        i = i + 1
        out2 = self.build_depthwise_separable_conv("CNN%d" % (i), out1, 3, 3, 16, 16, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)                                      
                                                  
        # building upsampling layer
        if self.scale == 1:
            # for AR network
            out6 = out2
        else:
            # for SR network          
            out6 = tf.depth_to_space(out2, self.scale)
        #update input pixels after calling depth to space
        self.pix_per_input = self.scale
        
        # compute the channels appropriately based on scale and depth2space        
        inp_ch_num = out_ch_num // (self.scale * self.scale)        
        
        # [3x3x16x8]
        i = i + 1
        out7 = self.build_conv("CNN%d" % (i), out6, 3, 3, inp_ch_num, 1, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)  

        # global residual
        self.y_ = tf.add(self.H[-1], self.x2, name="output")

        if self.save_weights:
            with tf.name_scope("Y_"):
                util.add_summaries("output", self.name, self.y_, save_stddev=True, save_mean=True)	        
 
        
    # Complex model
    def build_graph_v20_edge_concat(self):
        self.x = tf.placeholder(tf.float32, shape=[None, None, None, self.channels], name="x")
        self.y = tf.placeholder(tf.float32, shape=[None, None, None, self.output_channels], name="y")
        self.x2 = tf.placeholder(tf.float32, shape=[None, None, None, self.output_channels], name="x2")
        self.dropout = tf.placeholder(tf.float32, shape=[], name="dropout_keep_rate")
        self.is_training = tf.placeholder(tf.bool, name="is_training")

        # building feature extraction layers

        output_feature_num = self.filters
        total_output_feature_num = 0
        input_feature_num = self.channels
        input_tensor = self.x
		
        # custom architecture
        i = 0	

        if self.save_weights:
            with tf.name_scope("X"):
                util.add_summaries("output", self.name, self.x, save_stddev=True, save_mean=True)

        # [3x3x1x16]    
        i = i + 1        
        out1 = self.build_conv("CNN%d" % (i), input_tensor, 3, 3, input_feature_num, 16, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)                
         
        # [1x3x16x16]      
        i = i + 1
        out100 = self.build_conv("CNN%d" % (i), out1, 1, 3, 16, 16, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate) 
        out100 += out1
        
        # [1x3x16x16]      
        i = i + 1
        out101 = self.build_conv("CNN%d" % (i), out100, 1, 3, 16, 16, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate) 
                               
        # [1x3x16x16]      
        i = i + 1
        out2 = self.build_conv("CNN%d" % (i), out1, 1, 3, 16, 8, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)                               

        # [3x1x16x16]      
        i = i + 1
        out3 = self.build_conv("CNN%d" % (i), out1, 3, 1, 16, 8, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate) 
                                                       
        # concat
        out4 = tf.concat((out2, out3), 3, name="feature_concat")                                                                   
                  
        # [3x3x16x8]       
        i = i + 1
        out5 = self.build_conv("CNN%d" % (i), out4, 3, 3, 16, 8, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)  
                       
        # concat
        out6 = tf.concat((out1, out5), 3, name="feature_concat")    
        
        # dimension reduction
        # [1x1x24x16]        
        i = i + 1
        out7 = self.build_conv("CNN%d" % (i), out6, 1, 3, 24, 8, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate) 
                               
        # [1x1x24x16]        
        i = i + 1
        out8 = self.build_conv("CNN%d" % (i), out6, 3, 1, 24, 8, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)                           
         
        # concat
        out78 = tf.concat((out7, out8), 3, name="feature_concat") 
        
        # [3x3x16x8]       
        i = i + 1
        out9 = self.build_conv("CNN%d" % (i), out78, 3, 3, 16, 8, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)    
                               
        # concat
        out10 = tf.concat((out6, out9, out100, out101), 3, name="feature_concat")        
        
        # dimension reduction
        # [1x1x24x16]  
        out_ch_num = 32    
        i = i + 1
        out11 = self.build_depthwise_separable_conv("CNN%d" % (i), out10, 3, 3, 64, out_ch_num, use_bias=True, activator=self.activator,
                                    use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)         
                                                  
        # building upsampling layer
        if self.scale == 1:
            # for AR network
            out12 = out11
        else:
            # for SR network          
            out12 = tf.depth_to_space(out11, self.scale)
        #update input pixels after calling depth to space
        self.pix_per_input = self.scale
        
        # compute the channels appropriately based on scale and depth2space        
        inp_ch_num = out_ch_num // (self.scale * self.scale)
        # [3x3x16x8]
        i = i + 1
        out11 = self.build_conv("CNN%d" % (i), out12, 3, 3, inp_ch_num, 1, use_bias=True, activator=self.activator,
                               use_batch_norm=self.batch_norm, dropout_rate=self.dropout_rate)  

        # global residual
        self.y_ = tf.add(self.H[-1], self.x2, name="output")

        if self.save_weights:
            with tf.name_scope("Y_"):
                util.add_summaries("output", self.name, self.y_, save_stddev=True, save_mean=True)	        
                
        
    def build_graph(self):
        if self.arch_type == "dcscn":
            self.build_graph_dcscn()
        elif self.arch_type == "v1_edge_concat":
            self.build_graph_v1_edge_concat()
        elif self.arch_type == "v2_edge_concat":
            self.build_graph_v2_edge_concat()    
        elif self.arch_type == "v3_edge_concat":
            self.build_graph_v3_edge_concat()   
        elif self.arch_type == "v4_edge_concat":
            self.build_graph_v4_edge_concat()        
        elif self.arch_type == "v5_edge_concat":
            self.build_graph_v5_edge_concat()    
        elif self.arch_type == "v5_rzn":
            self.build_graph_v5_rzn()           
        elif self.arch_type == "v5_rzn_l":
            self.build_graph_v5_rzn_l()            
        elif self.arch_type == "v5_rzn_ul":
            self.build_graph_v5_rzn_ul()                             
        elif self.arch_type == "v5_3_edge_concat":
            self.build_graph_v5_3_edge_concat()    
        elif self.arch_type == "v5_4_edge_concat":
            self.build_graph_v5_4_edge_concat()   
        elif self.arch_type == "v5_car":
            self.build_graph_v5_car()               
        elif self.arch_type == "v6_edge_concat":
            self.build_graph_v6_edge_concat()  
        elif self.arch_type == "v6_1_edge_concat":
            self.build_graph_v6_1_edge_concat()              
        elif self.arch_type == "v6_2_edge_concat":
            self.build_graph_v6_2_edge_concat()     
        elif self.arch_type == "v6_3_edge_concat":
            self.build_graph_v6_3_edge_concat()              
        elif self.arch_type == "v7_edge_concat":
            self.build_graph_v7_edge_concat()  
        elif self.arch_type == "v7_1_edge_concat":
            self.build_graph_v7_1_edge_concat()              
        elif self.arch_type == "v8_edge_concat":
            self.build_graph_v8_edge_concat()  
        elif self.arch_type == "v8_1_edge_concat":
            self.build_graph_v8_1_edge_concat()              
        elif self.arch_type == "v9_edge_concat":
            self.build_graph_v9_edge_concat()     
        elif self.arch_type == "v9_1_edge_concat":
            self.build_graph_v9_1_edge_concat()    
        elif self.arch_type == "v33_edge_concat":
            self.build_graph_v33_edge_concat()               
        else:
            print("CNN Architecture name not supported, select supported architecture")
            
        self.print_network_stats()
    
    def build_optimizer(self):
        """
        Build loss function. We use 6+scale as a border	and we don't calculate MSE on the border.
        """

        self.lr_input = tf.placeholder(tf.float32, shape=[], name="LearningRate")

        diff = tf.subtract(self.y_, self.y, "diff")

        if self.use_l1_loss:
            self.mse = tf.reduce_mean(tf.square(diff, name="diff_square"), name="mse")
            self.image_loss = tf.reduce_mean(tf.abs(diff, name="diff_abs"), name="image_loss")
        else:
            self.mse = tf.reduce_mean(tf.square(diff, name="diff_square"), name="mse")
            self.image_loss = tf.identity(self.mse, name="image_loss")

        if self.l2_decay > 0:
            l2_norm_losses = [tf.nn.l2_loss(w) for w in self.Weights]
            l2_norm_loss = self.l2_decay * tf.add_n(l2_norm_losses)
            if self.enable_log:
                tf.summary.scalar("L2WeightDecayLoss/" + self.name, l2_norm_loss)

            self.loss = self.image_loss + l2_norm_loss
        else:
            self.loss = self.image_loss

        if self.enable_log:
            tf.summary.scalar("Loss/" + self.name, self.loss)

        if self.batch_norm:
            update_ops = tf.get_collection(tf.GraphKeys.UPDATE_OPS)
            with tf.control_dependencies(update_ops):
                self.training_optimizer = self.add_optimizer_op(self.loss, self.lr_input)
        else:
            self.training_optimizer = self.add_optimizer_op(self.loss, self.lr_input)

        util.print_num_of_total_parameters(output_detail=True)

    def get_psnr_tensor(self, mse):

        with tf.variable_scope('get_PSNR'):
            value = tf.constant(self.max_value, dtype=mse.dtype) / tf.sqrt(mse)
            numerator = tf.log(value)
            denominator = tf.log(tf.constant(10, dtype=mse.dtype))
            return tf.constant(20, dtype=mse.dtype) * numerator / denominator

    def add_optimizer_op(self, loss, lr_input):

        if self.optimizer == "gd":
            optimizer = tf.train.GradientDescentOptimizer(lr_input)
        elif self.optimizer == "adadelta":
            optimizer = tf.train.AdadeltaOptimizer(lr_input)
        elif self.optimizer == "adagrad":
            optimizer = tf.train.AdagradOptimizer(lr_input)
        elif self.optimizer == "adam":
            optimizer = tf.train.AdamOptimizer(lr_input, beta1=self.beta1, beta2=self.beta2, epsilon=self.epsilon)
        elif self.optimizer == "momentum":
            optimizer = tf.train.MomentumOptimizer(lr_input, self.momentum)
        elif self.optimizer == "rmsprop":
            optimizer = tf.train.RMSPropOptimizer(lr_input, momentum=self.momentum)
        else:
            print("Optimizer arg should be one of [gd, adadelta, adagrad, adam, momentum, rmsprop].")
            return None

        if self.clipping_norm > 0 or self.save_weights:
            trainables = tf.trainable_variables()
            grads = tf.gradients(loss, trainables)

            if self.save_weights:
                for i in range(len(grads)):
                    util.add_summaries("", self.name, grads[i], header_name=grads[i].name + "/", save_stddev=True,
                                       save_mean=True)

        if self.clipping_norm > 0:
            clipped_grads, _ = tf.clip_by_global_norm(grads, clip_norm=self.clipping_norm)
            grad_var_pairs = zip(clipped_grads, trainables)
            training_optimizer = optimizer.apply_gradients(grad_var_pairs)
        else:
            training_optimizer = optimizer.minimize(loss)

        return training_optimizer

    def train_batch(self):

        feed_dict = {self.x: self.batch_input, self.x2: self.batch_input_bicubic, self.y: self.batch_true,
                     self.lr_input: self.lr, self.dropout: self.dropout_rate, self.is_training: 1}

        _, image_loss, mse = self.sess.run([self.training_optimizer, self.image_loss, self.mse], feed_dict=feed_dict)
        self.training_loss_sum += image_loss
        self.training_psnr_sum += util.get_psnr(mse, max_value=self.max_value)

        self.training_step += 1
        self.step += 1

    def log_to_tensorboard(self, test_filename, psnr, save_meta_data=True):

        if self.enable_log is False:
            return

        # todo
        save_meta_data = False

        org_image = util.set_image_alignment(util.load_image(test_filename, print_console=False), self.scale)

        if len(org_image.shape) >= 3 and org_image.shape[2] == 3 and self.channels == 1:
            org_image = util.convert_rgb_to_y(org_image)

        input_image = util.resize_image_by_pil(org_image, 1.0 / self.scale, resampling_method=self.resampling_method)
        bicubic_image = util.resize_image_by_pil(input_image, self.scale, resampling_method=self.resampling_method)

        if self.max_value != 255.0:
            input_image = np.multiply(input_image, self.max_value / 255.0)  # type: np.ndarray
            bicubic_image = np.multiply(bicubic_image, self.max_value / 255.0)  # type: np.ndarray
            org_image = np.multiply(org_image, self.max_value / 255.0)  # type: np.ndarray

        feed_dict = {self.x: input_image.reshape([1, input_image.shape[0], input_image.shape[1], input_image.shape[2]]),
                     self.x2: bicubic_image.reshape(
                         [1, bicubic_image.shape[0], bicubic_image.shape[1], bicubic_image.shape[2]]),
                     self.y: org_image.reshape([1, org_image.shape[0], org_image.shape[1], org_image.shape[2]]),
                     self.dropout: 1.0,
                     self.is_training: 0}

        if save_meta_data:
            # profiler = tf.profiler.Profile(self.sess.graph)

            run_metadata = tf.RunMetadata()
            run_options = tf.RunOptions(trace_level=tf.RunOptions.FULL_TRACE)
            summary_str, _ = self.sess.run([self.summary_op, self.loss], feed_dict=feed_dict, options=run_options,
                                           run_metadata=run_metadata)
            self.test_writer.add_run_metadata(run_metadata, "step%d" % self.epochs_completed)

            filename = self.checkpoint_dir + "/" + self.name + "_metadata.txt"
            with open(filename, "w") as out:
                out.write(str(run_metadata))

            # filename = self.checkpoint_dir + "/" + self.name + "_memory.txt"
            # tf.profiler.write_op_log(
            # 	tf.get_default_graph(),
            # 	log_dir=self.checkpoint_dir,
            # 	#op_log=op_log,
            # 	run_meta=run_metadata)

            tf.contrib.tfprof.model_analyzer.print_model_analysis(
                tf.get_default_graph(), run_meta=run_metadata,
                tfprof_options=tf.contrib.tfprof.model_analyzer.PRINT_ALL_TIMING_MEMORY)

        else:
            summary_str, _ = self.sess.run([self.summary_op, self.loss], feed_dict=feed_dict)

        self.train_writer.add_summary(summary_str, self.epochs_completed)
        if not self.use_l1_loss:
            if self.training_step != 0:
                util.log_scalar_value(self.train_writer, 'PSNR', self.training_psnr_sum / self.training_step,
                                      self.epochs_completed)
        util.log_scalar_value(self.train_writer, 'LR', self.lr, self.epochs_completed)
        self.train_writer.flush()

        util.log_scalar_value(self.test_writer, 'PSNR', psnr, self.epochs_completed)
        self.test_writer.flush()

    def update_epoch_and_lr(self):

        # if warm_up true, dont update epoch steps till reach initial lr
        if self.warm_up > 0:
            if self.lr < self.initial_lr:
                self.lr += self.warm_up_lr_step
                return True
            else:
                # reset warmup
                self.warm_up = 0
            
        self.epochs_completed_in_stage += 1
        if self.epochs_completed_in_stage >= self.lr_decay_epoch:
            # set new learning rate
            self.lr *= self.lr_decay
            self.epochs_completed_in_stage = 0
            # restart lr logic
            if self.restart_lr_cnt > 0:
                if self.lr < self.restart_lr_threshold:
                    self.restart_lr_cnt -= 1            
                    # reduce threshold by 0.75
                    self.restart_lr_threshold *= 0.4
                    self.lr = self.lr * 6 #self.restart_lr       
                    self.restart_lr *= 0.75                    
                    logging.info("\n Learning rate restarted... ")
                    logging.info("\n New lr: {}, Next lr threshold: {}".format(self.lr, self.restart_lr_threshold))
            return True
        else:
            return False

    def print_network_stats(self):
        logging.info("\n++++++++ Network Complexity Statistics ++++++++ ")				
        logging.info("Feature:%s Receptive Fields:%d" % (self.features, self.receptive_fields))
        logging.info("Complexity_Conv:%s Complexity_Total:%s" % (
            "{:,}".format(self.complexity_conv), "{:,}".format(self.complexity)))	
        i = 0
        logging.info("\n----- Complexity statistics for each conv layer -----")
        logging.info("Layer        pwxph x kwxkh x inpCxoutC")
        for param in self.complexity_conv_param:
            logging.info("conv%2d: %30s: #mac:%5d" % (i + 1, param, self.complexity_conv_mac[i]))
            i = i + 1
        logging.info("\n")	    
            
    def print_status(self, data_set, psnr, ssim, psnr_rgb, ssim_rgb, log=False):

        if self.step == 0:
            logging.info("[test-set: %s]: Initial PSNR_Y:%f SSIM_Y:%f -- PSNR_RGB:%f SSIM_RGB:%f" % (data_set, psnr, ssim, psnr_rgb, ssim_rgb))
        else:
            processing_time = (time.time() - self.start_time) / self.step                 
            estimated = processing_time * (self.total_epochs - self.epochs_completed) * (
                self.training_images // self.batch_num)
            h = estimated // (60 * 60)
            estimated -= h * 60 * 60
            m = estimated // 60
            s = estimated - m * 60
 
            line_a = "%s\n Epoch:%d, Step:%s, LR:%f (%2.3fsec/step) Estimated:%d:%d:%d " % (util.get_now_date(), self.epochs_completed, 
                        "{:,}".format(self.step), self.lr, processing_time, h, m, s)
            if self.use_l1_loss:
                line_b = "[test-set: %s] PSNR_Y=%0.3f SSIM_Y=%0.5f -- PSNR_RGB=%0.3f SSIM_RGB=%0.5f  (Training Loss=%0.3f)" % (
                    data_set, psnr, ssim, psnr_rgb, ssim_rgb, self.training_loss_sum / self.training_step)                    
            else:
                line_b = "[test-set: %s] PSNR_Y=%0.3f SSIM_Y=%0.5f -- PSNR_RGB=%0.3f SSIM_RGB=%0.5f (Train PSNR=%0.3f)" % (
                    data_set, psnr, ssim, psnr_rgb, ssim_rgb, self.training_psnr_sum / self.training_step)              

            if log:
                logging.info(line_a)
                logging.info(line_b)
            else:
                print(line_a)
                print(line_b)

    def print_weight_variables(self):

        for bias in self.Biases:
            util.print_filter_biases(bias)

        for weight in self.Weights:
            util.print_filter_weights(weight)

    def evaluate(self, test_filenames):

        total_psnr = total_ssim = 0
        total_psnr_rgb = total_ssim_rgb = 0
        if len(test_filenames) == 0:
            return 0, 0

        for filename in test_filenames:
            psnr, ssim, psnr_rgb, ssim_rgb = self.do_for_evaluate(filename, print_console=False)
            total_psnr += psnr
            total_ssim += ssim
            total_psnr_rgb += psnr_rgb
            total_ssim_rgb += ssim_rgb
            
        return total_psnr / len(test_filenames), total_ssim / len(test_filenames), total_psnr_rgb / len(test_filenames), total_ssim_rgb / len(test_filenames)

    def do(self, input_image, bicubic_input_image=None):

        h, w = input_image.shape[:2]
        ch = input_image.shape[2] if len(input_image.shape) > 2 else 1

        if bicubic_input_image is None:
            bicubic_input_image = util.resize_image_by_pil(input_image, self.scale,
                                                           resampling_method=self.resampling_method)
        if self.max_value != 255.0:
            input_image = np.multiply(input_image, self.max_value / 255.0)  # type: np.ndarray
            bicubic_input_image = np.multiply(bicubic_input_image, self.max_value / 255.0)  # type: np.ndarray

        if self.self_ensemble > 1:
            output = np.zeros([self.scale * h, self.scale * w, 1])

            for i in range(self.self_ensemble):
                image = util.flip(input_image, i)
                bicubic_image = util.flip(bicubic_input_image, i)
                y = self.sess.run(self.y_, feed_dict={self.x: image.reshape(1, image.shape[0], image.shape[1], ch),
                                                      self.x2: bicubic_image.reshape(1, self.scale * image.shape[0],
                                                                                     self.scale * image.shape[1],
                                                                                     ch),
                                                      self.dropout: 1.0, self.is_training: 0})
                restored = util.flip(y[0], i, invert=True)
                output += restored

            output /= self.self_ensemble
        else:
            y = self.sess.run(self.y_, feed_dict={self.x: input_image.reshape(1, h, w, ch),
                                                  self.x2: bicubic_input_image.reshape(1, self.scale * h,
                                                                                       self.scale * w, ch)})
            output = y[0]

        if self.max_value != 255.0:
            hr_image = np.multiply(output, 255.0 / self.max_value)
        else:
            hr_image = output

        return hr_image

    def do_for_file(self, file_path, output_folder="output"):

        org_image = util.load_image(file_path)

        filename, extension = os.path.splitext(os.path.basename(file_path))
        output_folder += "/" + self.name + "/"
        util.save_image(output_folder + filename + extension, org_image)

        scaled_image = util.resize_image_by_pil(org_image, self.scale, resampling_method=self.resampling_method)
        util.save_image(output_folder + filename + "_bicubic" + extension, scaled_image)

        if len(org_image.shape) >= 3 and org_image.shape[2] == 3 and self.channels == 1:
            input_y_image = util.convert_rgb_to_y(org_image)
            scaled_image = util.resize_image_by_pil(input_y_image, self.scale, resampling_method=self.resampling_method)
            util.save_image(output_folder + filename + "_bicubic_y" + extension, scaled_image)
            output_y_image = self.do(input_y_image)
            util.save_image(output_folder + filename + "_result_y" + extension, output_y_image)

            scaled_ycbcr_image = util.convert_rgb_to_ycbcr(
                util.resize_image_by_pil(org_image, self.scale, self.resampling_method))
            image = util.convert_y_and_cbcr_to_rgb(output_y_image, scaled_ycbcr_image[:, :, 1:3])
        else:
            scaled_image = util.resize_image_by_pil(org_image, self.scale, resampling_method=self.resampling_method)
            util.save_image(output_folder + filename + "_bicubic_y" + extension, scaled_image)
            image = self.do(org_image)

        util.save_image(output_folder + filename + "_result" + extension, image)

    def do_for_evaluate_with_output(self, file_path, output_directory, print_console=False):

        filename, extension = os.path.splitext(file_path)
        output_directory += "/" + self.name + "/"
        util.make_dir(output_directory)

        true_image = util.set_image_alignment(util.load_image(file_path, print_console=False), self.scale)
        input_image = util.resize_image_by_pil(true_image, 1.0/ self.scale, resampling_method=self.resampling_method)
        input_bicubic_image = util.resize_image_by_pil(input_image, self.scale, resampling_method=self.resampling_method)
        # RGB-HR (bicubic): down-scaled and up-scaled image
        #util.save_image(output_directory + filename + "_input_bicubic" + extension, input_bicubic_image)

        psnr = ssim = psnr_rgb = ssim_rgb = 0
        if true_image.shape[2] == 3 and self.channels == 1:

            true_ycbcr_image = util.convert_rgb_to_ycbcr(true_image)        
            
            if self.compress_input_q > 1:
                input_y_image, u_lr, v_lr = util.compress_with_jpeg(true_image, self.compress_input_q, self.scale, self.resampling_method)
                # bicubic upscale YUV channels (Y for network input, UV for final output)
            else:
                # for color images
                input_y_image = loader.build_input_image(true_image, channels=self.channels, scale=self.scale,
                                                        alignment=self.scale, convert_ycbcr=True)
    
                # create u,v LR images from HR u,v
                u_lr = util.resize_image_by_pil(true_ycbcr_image[:,:,1:2], 1.0/ self.scale, resampling_method=self.resampling_method)
                v_lr = util.resize_image_by_pil(true_ycbcr_image[:,:,2:3], 1.0/ self.scale, resampling_method=self.resampling_method)
                
            # bicubic up-scale y channels
            input_bicubic_y_image = util.resize_image_by_pil(input_y_image, self.scale, resampling_method=self.resampling_method)                
            # bicubic up-scale u, v channels
            u_hr = util.resize_image_by_pil(u_lr, self.scale, resampling_method=self.resampling_method)
            v_hr = util.resize_image_by_pil(v_lr, self.scale, resampling_method=self.resampling_method)

            # Network inference
            output_y_image = self.do(input_y_image, input_bicubic_y_image)
            
            # compute Y PSNR, SSIM
            psnr, ssim = util.compute_psnr_and_ssim(true_ycbcr_image[:, :, 0:1], output_y_image,
                                                    border_size=self.psnr_calc_border_size)
            # get loss image
            #loss_image = util.get_loss_image(true_ycbcr_image[:, :, 0:1], output_y_image,
            #                                 border_size=self.psnr_calc_border_size)

            #output_color_image = util.convert_y_and_cbcr_to_rgb(output_y_image, true_ycbcr_image[:, :, 1:3])
            # create color image from model upscaling (Y) and bicubic (uv)
            uv_image = np.zeros([u_hr.shape[0], u_hr.shape[1], 2])
            uv_image[:, :, 0] = u_hr[:, :, 0]
            uv_image[:, :, 1] = v_hr[:, :, 0]
            output_color_image = util.convert_y_and_cbcr_to_rgb(output_y_image, uv_image)
            
            # compute RGB PSNR, SSIM
            psnr_rgb, ssim_rgb = util.compute_psnr_and_ssim(true_image, output_color_image,
                                                    border_size=self.psnr_calc_border_size)            

            #util.save_image(output_directory + file_path, true_image)
            # Y-LR: input to model, rgb2yuv converted and downscaled
            #util.save_image(output_directory + filename + "_input" + extension, input_y_image)
            # Y-HR (bicubic): downscaled and upscaled with bicubic
            #util.save_image(output_directory + filename + "_input_bicubic_y" + extension, input_bicubic_y_image)
            # Y-HR: Actual input
            #util.save_image(output_directory + filename + "_true_y" + extension, true_ycbcr_image[:, :, 0:1])
            # Y-HR: Model output
            #util.save_image(output_directory + filename + "_result" + extension, output_y_image)
            util.save_image(output_directory + filename + "_result_c" + extension, output_color_image)
            #util.save_image(output_directory + filename + "_loss" + extension, loss_image)

        elif true_image.shape[2] == 1 and self.channels == 1:

            # for monochrome images
            if self.compress_input_q > 1:
                input_image, u_lr, v_lr = util.compress_with_jpeg(true_image, self.compress_input_q, self.scale, self.resampling_method)
            else:
                input_image = loader.build_input_image(true_image, channels=self.channels, scale=self.scale, alignment=self.scale)
            input_bicubic_y_image = util.resize_image_by_pil(input_image, self.scale, resampling_method=self.resampling_method)
            output_image = self.do(input_image, input_bicubic_y_image)
            psnr, ssim = util.compute_psnr_and_ssim(true_image, output_image, border_size=self.psnr_calc_border_size)
            util.save_image(output_directory + file_path, true_image)
            util.save_image(output_directory + filename + "_result" + extension, output_image)
        else:
            return None, None, None, None

        if print_console:
            logging.info("[%s] PSNR_Y  :%f, SSIM_Y  :%f" % (filename, psnr, ssim))
            logging.info("[%s] PSNR_RGB:%f, SSIM_RGB:%f" % (filename, psnr_rgb, ssim_rgb))

        return psnr, ssim, psnr_rgb, ssim_rgb

    def do_for_evaluate(self, file_path, print_console=False):

        true_image = util.set_image_alignment(util.load_image(file_path, print_console=False), self.scale)

        psnr = ssim = psnr_rgb = ssim_rgb = 0
        if true_image.shape[2] == 3 and self.channels == 1:

            true_ycbcr_image = util.convert_rgb_to_ycbcr(true_image)                                                    
            
            if self.compress_input_q > 1:     
                input_y_image, u_lr, v_lr = util.compress_with_jpeg(true_image, self.compress_input_q, self.scale, self.resampling_method)
            else:
                # for color images
                input_y_image = loader.build_input_image(true_image, channels=self.channels, scale=self.scale,
                                                        alignment=self.scale, convert_ycbcr=True)
                # down-scale u,v channels
                u_lr = util.resize_image_by_pil(true_ycbcr_image[:,:,1:2], 1.0/ self.scale, resampling_method=self.resampling_method)
                v_lr = util.resize_image_by_pil(true_ycbcr_image[:,:,2:3], 1.0/ self.scale, resampling_method=self.resampling_method)
                                                        
            true_y_image = util.convert_rgb_to_y(true_image)
            # bicubic up-scale y channels
            input_bicubic_y_image = util.resize_image_by_pil(input_y_image, self.scale, resampling_method=self.resampling_method)
            # bicubic up-scale u, v channels
            u_hr = util.resize_image_by_pil(u_lr, self.scale, resampling_method=self.resampling_method)
            v_hr = util.resize_image_by_pil(v_lr, self.scale, resampling_method=self.resampling_method)
            
            # Network inference
            output_y_image = self.do(input_y_image, input_bicubic_y_image)
            
            # compute Y PSNR, SSIM
            psnr, ssim = util.compute_psnr_and_ssim(true_y_image, output_y_image, border_size=self.psnr_calc_border_size)
            
            # create color image from model upscaling (Y) and bicubic (uv)
            uv_image = np.zeros([u_hr.shape[0], u_hr.shape[1], 2])
            uv_image[:, :, 0] = u_hr[:, :, 0]
            uv_image[:, :, 1] = v_hr[:, :, 0]
            output_color_image = util.convert_y_and_cbcr_to_rgb(output_y_image, uv_image)
            # compute RGB PSNR, SSIM
            psnr_rgb, ssim_rgb = util.compute_psnr_and_ssim(true_image, output_color_image,
                                                    border_size=self.psnr_calc_border_size)            
                                                    
        elif true_image.shape[2] == 1 and self.channels == 1:

            # for monochrome images
            if self.compress_input_q > 1:
                input_image, u_lr, v_lr = util.compress_with_jpeg(true_image, self.compress_input_q, self.scale, self.resampling_method)
            else:            
                input_image = loader.build_input_image(true_image, channels=self.channels, scale=self.scale, alignment=self.scale)
            input_bicubic_y_image = util.resize_image_by_pil(input_image, self.scale, resampling_method=self.resampling_method)
            output_image = self.do(input_image, input_bicubic_y_image)
            psnr, ssim = util.compute_psnr_and_ssim(true_image, output_image, border_size=self.psnr_calc_border_size)
        else:
            return None, None, None, None

        if print_console:
            logging.info("[%s] PSNR_Y  :%f, SSIM_Y  :%f" % (file_path, psnr, ssim))
            logging.info("[%s] PSNR_RGB:%f, SSIM_RGB:%f" % (file_path, psnr_rgb, ssim_rgb))            

        return psnr, ssim, psnr_rgb, ssim_rgb

    def evaluate_bicubic(self, file_path, print_console=False):

        psnr = ssim = psnr_rgb = ssim_rgb = 0
        true_image = util.set_image_alignment(util.load_image(file_path, print_console=False), self.scale)

        if true_image.shape[2] == 3 and self.channels == 1:
            if self.compress_input_q > 1:
                # compress input image
                input_y_image, u_lr, v_lr = util.compress_with_jpeg(true_image, self.compress_input_q, self.scale, self.resampling_method)
                input_image = input_y_image
            else:
                input_image_yuv = loader.build_input_image(true_image, channels=self.channels, scale=self.scale,
                                                    alignment=self.scale, convert_ycbcr=True)
                input_image = input_image_yuv[:,:,0:1]
                u_lr = input_image_yuv[:,:,1:2]
                v_lr = input_image_yuv[:,:,2:3]
                
            true_image_y = util.convert_rgb_to_y(true_image)
        elif true_image.shape[2] == 1 and self.channels == 1:
            # for monochrome images
            if self.compress_input_q > 1:
                input_image, u_lr, v_lr = util.compress_with_jpeg(true_image, self.compress_input_q, self.scale, self.resampling_method)
            else:            
                input_image = loader.build_input_image(true_image, channels=self.channels, scale=self.scale, alignment=self.scale)
            true_image_y = true_image
        else:
            return None, None, None, None

        input_bicubic_image = util.resize_image_by_pil(input_image, self.scale, resampling_method=self.resampling_method)
        psnr, ssim = util.compute_psnr_and_ssim(true_image_y, input_bicubic_image, border_size=self.psnr_calc_border_size)

        #print("true_image.shape:{}, input_image_yuv.shape: {}, u_lr.shape: {}, input_image.shape: {}, file_path: {}".format(true_image.shape, input_image_yuv.shape, u_lr.shape, input_image.shape, file_path))
        if self.compress_input_q > 1 and true_image.shape[2] == 3 and self.channels == 1:
            # bicubic up-scale u, v channels
            u_hr = util.resize_image_by_pil(u_lr, self.scale, resampling_method=self.resampling_method)
            v_hr = util.resize_image_by_pil(v_lr, self.scale, resampling_method=self.resampling_method)        
            # create color image from model upscaling (Y) and bicubic (uv)
            uv_image = np.zeros([u_hr.shape[0], u_hr.shape[1], 2])
            uv_image[:, :, 0] = u_hr[:, :, 0]
            uv_image[:, :, 1] = v_hr[:, :, 0]
            output_color_image = util.convert_y_and_cbcr_to_rgb(input_bicubic_image, uv_image)
            # compute RGB PSNR, SSIM
            psnr_rgb, ssim_rgb = util.compute_psnr_and_ssim(true_image, output_color_image,
                                                    border_size=self.psnr_calc_border_size)                        
            
        if print_console:
            logging.info("PSNR:%f, SSIM:%f" % (psnr, ssim))

        return psnr, ssim, psnr_rgb, ssim_rgb

    def init_train_step(self):
        self.lr = self.initial_lr
        if self.warm_up > 0:
            self.lr = self.warm_up_lr
        self.epochs_completed = 0
        self.epochs_completed_in_stage = 0
        self.min_validation_mse = -1
        self.min_validation_epoch = -1
        self.step = 0

        self.start_time = time.time()

    def end_train_step(self):
        self.total_time = time.time() - self.start_time

    def print_steps_completed(self, output_to_logging=False):

        if self.step == 0:
            return

        processing_time = self.total_time / self.step
        h = self.total_time // (60 * 60)
        m = (self.total_time - h * 60 * 60) // 60
        s = (self.total_time - h * 60 * 60 - m * 60)

        status = "Finished at Total Epoch:%d Steps:%s Time:%02d:%02d:%02d (%2.3fsec/step) %d x %d x %d patches" % (
            self.epochs_completed, "{:,}".format(self.step), h, m, s, processing_time,
            self.batch_image_size, self.batch_image_size, self.training_images)

        if output_to_logging:
            logging.info(status)
        else:
            print(status)

    def log_model_analysis(self):
        run_metadata = tf.RunMetadata()
        run_options = tf.RunOptions(trace_level=tf.RunOptions.FULL_TRACE)

        _, loss = self.sess.run([self.optimizer, self.loss], feed_dict={self.x: self.batch_input,
                                                                        self.x2: self.batch_input_bicubic,
                                                                        self.y: self.batch_true,
                                                                        self.lr_input: self.lr,
                                                                        self.dropout: self.dropout_rate},
                                options=run_options, run_metadata=run_metadata)

        # tf.contrib.tfprof.model_analyzer.print_model_analysis(
        #   tf.get_default_graph(),
        #   run_meta=run_metadata,
        #   tfprof_options=tf.contrib.tfprof.model_analyzer.PRINT_ALL_TIMING_MEMORY)
        self.first_training = False
