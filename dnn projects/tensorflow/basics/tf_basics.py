import tensorflow as tf
hello = tf.constant('Hello, TensorFlow!')
sess = tf.Session()
print(sess.run(hello))

# write graph
writer = tf.summary.FileWriter("/home/sirish/Desktop/learning-git/dnn projects/tensorflow/basics/")
writer.add_graph(sess.graph)

