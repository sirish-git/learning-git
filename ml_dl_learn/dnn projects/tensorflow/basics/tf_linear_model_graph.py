import tensorflow as tf
import numpy as np
import matplotlib.pyplot as plt

#variables
w = tf.Variable([0.3], tf.float32, name='weight')
b = tf.Variable([-0.3], tf.float32, name='bias')
#place holder
x = tf.placeholder(tf.float32, name='input')
train_x = np.asarray([1,2,3,4])
#liner model
linear_net = w * x + b
#expected output
y = tf.placeholder(tf.float32, name='label_output')
train_y = np.asarray([0,-1,-2,-3])

#loss
sqr_dif = tf.square(linear_net - y)
loss = tf.reduce_sum(sqr_dif)

#optimizer
optimizer = tf.train.GradientDescentOptimizer(0.01)
train = optimizer.minimize(loss)

#init
init = tf.global_variables_initializer()

# add histograms
tf.summary.histogram('weights1', w)
tf.summary.histogram('biases1', b)
merged_summary = tf.summary.merge_all()
# write graph
writer = tf.summary.FileWriter("/home/sirish/Desktop/learning-git/dnn projects/tensorflow/basics/")

with tf.Session() as sess:
    sess.run(init)

    #graph related
    writer.add_graph(sess.graph)

    #train network
    for i in range(1000):
        out, summary_out = sess.run([train, merged_summary], feed_dict={x:train_x, y:train_y})
        writer.add_summary(summary_out)

    #graph related
    writer.close()

    #save the model
    saver = tf.train.Saver()
    saver.save(sess, './test_model')

    print (sess.run([w, b]))

    plt.plot(train_x, train_y, 'ro', label='original data')
    plt.plot(train_x, sess.run(w)*train_x+sess.run(b), label='fitted-line')
    plt.legend()
    plt.show()