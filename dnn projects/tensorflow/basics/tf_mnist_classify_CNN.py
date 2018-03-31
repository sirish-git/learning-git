import tensorflow as tf
#import mnist input data
import tensorflow.examples.tutorials.mnist.input_data as input_data

#read input data
mnist = input_data.read_data_sets("/tmp/data", one_hot=True)

#training params
learning_rate = 0.001
num_steps = 500
batch_size = 128
display_step = 10

#network params
num_inputs = 784
num_classes = 10
dropout = 0.75

#graph input/output
X = tf.placeholder(tf.float32, [None, num_inputs], name='input')
Y = tf.placeholder(tf.float32, [None, num_classes], name='correct_classes')
keep_prob = tf.placeholder(tf.float32)

#wrapper functions for simplicity
def conv2d(x, W, b, strides=1):
    ''' Conv2d wrapper with bias and relu activation'''
    x = tf.nn.conv2d(x, W, strides=[1, strides, strides, 1], padding='SAME', name='conv2d')
    x = tf.nn.bias_add(x, b, name='bias_add')
    return tf.nn.relu(x, name='relu')

def maxpool2d(x, k=2):
    ''' maxpool2d '''
    return tf.nn.max_pool(x, ksize=[1, k, k, 1], strides=[1, k, k, 1], padding='SAME')

#create model
def create_model(x, weights, biases, dropout):
    #reshape input as image tensor
    x = tf.reshape(x, shape=[-1, 28, 28, 1])

    #convol layer
    conv1 = conv2d(x, weights['wc1'], biases['bc1'])
    #max pool
    max_pool1 = maxpool2d(conv1)

    #convol layer
    conv2 = conv2d(max_pool1, weights['wc2'], biases['bc2'])
    max_pool2 = maxpool2d(conv2)

    #fc layer
    #reshape input as 1d
    fc_inp = tf.reshape(max_pool2, shape=[-1, weights['wf3'].get_shape().as_list()[0]])
    fc1 = tf.add(tf.matmul(fc_inp, weights['wf3']), biases['bf3'])
    fc1 = tf.nn.relu(fc1)

    #apply droput
    fc1 = tf.nn.dropout(fc1, dropout)

    #output class prediction
    out = tf.add(tf.matmul(fc1, weights['out']), biases['out'])
    return out

#define weights and biases
weights = {
    #conv 5x5, 1 input, 32 output
    'wc1' : tf.Variable(tf.random_normal([5, 5, 1, 32])),
    #conv 5x5, 32 input, 64 output
    'wc2' : tf.Variable(tf.random_normal([5, 5, 32, 64])),
    #fc 7x7x64 inputs, 1024 outputs
    'wf3' : tf.Variable(tf.random_normal([7*7*64, 1024])),
    #output 1024 input, 10 output
    'out' : tf.Variable(tf.random_normal([1024, num_classes]))
}

biases = {
    #conv1, 32 outputs
    'bc1' : tf.Variable(tf.random_normal([32])),
    #conv2, 64 outputs
    'bc2' : tf.Variable(tf.random_normal([64])),
    #fc, 1024 outputs
    'bf3' : tf.Variable(tf.random_normal([1024])),
    #output
    'out' : tf.Variable(tf.random_normal([num_classes]))
}


#construct model
logits = create_model(X, weights, biases, keep_prob)
pred = tf.nn.softmax(logits)

#define loss, optimizer
loss_op = tf.nn.softmax_cross_entropy_with_logits(logits=logits, labels=Y)
loss_op = tf.reduce_mean(loss_op)
optimizer = tf.train.AdamOptimizer(learning_rate=learning_rate)
train = optimizer.minimize(loss_op)

#evaluate model
correct_pred = tf.equal(tf.argmax(pred, 1), tf.argmax(Y, 1))
accuracy = tf.reduce_mean(tf.cast(correct_pred, tf.float32))

#init
init = tf.global_variables_initializer()


# start training
with tf.Session() as sess:
    #init
    sess.run(init)

    for step in range(1, num_steps+1):
        #get next batch
        batch_x, batch_y = mnist.train.next_batch(batch_size)
        #run back prop
        sess.run(train, feed_dict={X:batch_x, Y:batch_y, keep_prob:dropout})

        if step % display_step == 0 or step == 1:
            # Calculate batch loss and accuracy
            loss, acc = sess.run([loss_op, accuracy], feed_dict={X: batch_x,
                                                                 Y: batch_y,
                                                                 keep_prob: 1.0})
            print("Step " + str(step) + ", Minibatch Loss= " + \
                  "{:.4f}".format(loss) + ", Training Accuracy= " + \
                  "{:.3f}".format(acc))

    #save the model
    saver = tf.train.Saver()
    saver.save(sess, 'mnist_classify_cnn')

    print("Optimization Finished!")

    # Calculate accuracy for 256 MNIST test images
    print("Testing Accuracy:", \
        sess.run(accuracy, feed_dict={X: mnist.test.images[:256],
                                      Y: mnist.test.labels[:256],
                                      keep_prob: 1.0}))