import tensorflow as tf

with tf.Session() as sess:
    #load pre trained
    saver = tf.train.import_meta_graph('test_model.meta')
    saver.restore(sess, tf.train.latest_checkpoint('./'))
    print sess.run('b')