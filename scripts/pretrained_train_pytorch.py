from __future__ import print_function
from __future__ import division

# Torch imports
import torch
from torch.utils.data import DataLoader
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
# from torch.optim import lr_scheduler
from torch.autograd import Variable

# Other python imports
import numpy as np
import argparse
import matplotlib.pyplot as plt
import cPickle as pickle
import pdb
from matplotlib.backends.backend_pdf import PdfPages
# Other py files imports
from constants import *
from pretrained_models_pytorch import *
from config import *
from Salicon_loader import *

#-------------------------------------------------------------
# Argument parsing and exporting torch to cuda.
args = parser.parse_args()
args.cuda = not args.no_cuda and torch.cuda.is_available()

torch.manual_seed(args.seed)
if args.cuda:
    torch.cuda.manual_seed(args.seed)

# # Salicon Data Processing
# #-------------------------------------------------------------

# trainimages = np.load("../../Cookingdata.npy")
# trainmasks = np.load("../../Cookingdata_masks.npy")

trainimages = np.load(trainImagesPath)
trainmasks = np.load(trainMasksPath)
# pdb.set_trace
# testimages = np.load(testImagesPath)
# testmasks = np.load(testMasksPath)

    # Load Training Data via dataloader object (Salicon_loader.py). Data for the network is Images and the ground truth label is saliency map.
train_dataloader_obj = Salicon_loader(trainimages,trainmasks)    
trainloader = DataLoader(train_dataloader_obj, batch_size=args.batch_size, shuffle=True, num_workers=2)
  
    # Load Testing Data via dataloader object (Salicon_loader.py).
# test_dataloader_obj = Salicon_loader(testimages,testmasks)
# testloader = DataLoader(test_dataloader_obj, batch_size=args.test_batchsize, shuffle=False, num_workers=2)

# Choosing a Network Architecture
# --------------------------------------------------------------

print (" 2.1 --> Building the network with Salgan model")

        # Deploying the generator network model from models-pytorch.py

# g1_net = Generator()
g_net = torch.load('../gen_model_final.pt')
d_net = torch.load('../disc_model_final.pt')

# g_net = torch.load('../gen_model_epoch30.pt')
# d_net = torch.load('../disc_model_epoch30.pt')


# g_net.load_state_dict(torch.load('gen_model.pt'))
        # Deploying the discriminator network model from models-pytorch.py
# d_net = Discriminator()
        # Content Loss used by the Generator during training.
BCELoss= nn.BCELoss().cuda()

if args.cuda:
    g_net.cuda()
    d_net.cuda()   


        # Using Adagrad optimizer with initial learning rate of 3e-4 and weight decay of 1e-4 
gen_trainable_params  = filter(lambda p: p.requires_grad, g_net.parameters())

optimizer_gen = optim.Adagrad(gen_trainable_params, lr=args.lr, weight_decay = args.wd) # Look into this later
optimizer_disc = optim.Adagrad(d_net.parameters(), lr=args.lr, weight_decay = args.wd)

contentloss = []
discrimloss = []



def plot_images(images, true_saliency, pred_saliency,id):
    # for i in np.random.randint(np.shape(images)[0], size=10):
    for i in range(32):
        fig = plt.figure(i)
        ax1 = fig.add_subplot(131)
        surf = ax1.imshow(images[i,:,:,:].astype(np.uint8))
        ax1.set_title('Image')
        ax2 = fig.add_subplot(132)
        surf = ax2.imshow(true_saliency[i,:,:])
        ax2.set_title('True Saliency')
        ax3 = fig.add_subplot(133)
        surf = ax3.imshow(pred_saliency[i,:,:])
        ax3.set_title('Predicted Saliency')

        # plt.cla()

        # pred_weighted_image = np.multiply(images[26,:,:,:],(np.expand_dims(pred_saliency[26,:,:],axis=3))).astype(np.uint8)
        # true_weighted_image = np.multiply(images[26,:,:,:],(np.expand_dims(pred_saliency[26,:,:],axis=3)/255.0)).astype(np.uint8)
    # plt.show()
    
    def multipage(filename, figs=None, dpi=200):
        pp = PdfPages(filename)
        if figs is None:
            figs = [plt.figure(n) for n in plt.get_fignums()]
        for fig in figs:
            fig.savefig(pp, format='pdf')
        pp.close()

    filename = 'plot_batch_mid{}.pdf'.format(id)
    multipage(filename, dpi=250)

    

 # Exponential learning rate decay
def adjust_learning_rate(optimizer, epoch):
    """Sets the learning rate to the initial LR decayed by 10 every 5 epochs"""
    decay_factor = (args.min_lr / args.lr)**(epoch//5)
    lr = args.lr * decay_factor
    for param_group in optimizer_gen.param_groups:
        param_group['lr'] = lr

def train(epoch):
    # g_net.train()
    # d_net.train()

    g_net.eval()
    d_net.eval()

    if epoch <= args.epochs_gen: 
        print (" Only Generator Training")
    else:
        print ("Adversarial Training")

    for batch_idx, (image, true_saliency) in enumerate(trainloader):
        if args.cuda:
            image, true_saliency = image.cuda(), true_saliency.cuda()
        
        image = image.squeeze()
        image, true_saliency = Variable(image), Variable(true_saliency)             

                        # Evaluating the GAN Network
                    #-----------------------------------------    
            # Generate the predicted saliency map from the generator network.      
        # pred_saliency1 = g_net(image)
        pred_saliency = g_net(image)

        PLOT_FLAG = args.plot_saliency
        
        if PLOT_FLAG:
            images = (image.cpu().data.numpy().transpose([0,2,3,1]) + np.array([103.939, 116.779, 123.68]).reshape(1,1,1,3))[:,:,:,::-1]
            true_saliencies = true_saliency.squeeze().cpu().data.numpy()            
            pred_saliencies = pred_saliency.squeeze().cpu().data.numpy()
            pdb.set_trace()

            # plt.clf()
            # plt.cla()
            # plt.close('all')

            plot_images(images, true_saliencies, pred_saliencies,batch_idx)
            image_fixated = images*(np.repeat(pred_saliencies[:,:,:,np.newaxis],3,axis=3))
            pdb.set_trace()
            PLOT_FLAG = False        

            # Concatenate the predicted saliency map to the original image so that it can be fed into the discriminator network. RGBS Image = 256 x 192 x 4
        stacked_image = torch.cat((image,pred_saliency),1)
        
        pred_saliency = pred_saliency.squeeze() 

            #Feeding the stacked image with saliency map to the discriminator network to get a single probability value that tells us the probability of fooling the network
        

        # Bootstrap the network for first 15 epochs using only the BCE Content Loss and then add the discriminator
        #------------------------------------------------------------------------------------------------------------
        if epoch<=args.epochs_gen:

                        # Only Generator Training (No Discriminator Training)
            # Calculating the Content Loss between predicted saliency map and ground truth saliency map.

            # Remember to add Downscale Saliency maps for prediction and ground truth for BCE loss.
                      
            gen_loss = BCELoss(pred_saliency,true_saliency) 
            # pdb.set_trace()
            contentloss.append(gen_loss.data[0])

            optimizer_gen.zero_grad()
            gen_loss.backward()
            optimizer_gen.step()

            if batch_idx % args.log_interval == 0:
                print('Train Epoch: {} [{}/{} ({:.0f}%)]\tContent_Loss: {:.6f}'.format(
                    epoch, batch_idx * len(image), len(trainloader.dataset),
                    100. * batch_idx / len(trainloader), gen_loss.data[0]))

        else:
                                 # Adversarial Training
            
            # During the adversarial Training, the training of the generator and discriminator is alternated after each batch 
            dis_output = d_net(stacked_image)
            # pdb.set_trace()
            if (batch_idx%2)==0:
                            # Generator Training  
                    # Calculating the Content Loss between predicted saliency map and ground truth saliency map.
                content_loss = BCELoss(pred_saliency,true_saliency)        
                    # Calculating the Adversarial loss
                disc_loss = torch.mean(-torch.log(dis_output))
                    # The final loss function of the generator i.e. GAN Loss is defined as 
                gen_loss = (args.alpha*content_loss) + disc_loss

                contentloss.append(content_loss.data[0])
                discrimloss.append(disc_loss.data[0])

                optimizer_gen.zero_grad()
                gen_loss.backward()
                optimizer_gen.step()

                if batch_idx % args.log_interval == 0:
                    print('Train Epoch: {} [{}/{} ({:.0f}%)]\tContent Loss: {:.6f}\tDiscriminator Loss: {:.6f}'.format(
                    epoch, batch_idx * len(image), len(trainloader.dataset),
                    100. * batch_idx / len(trainloader), content_loss.data[0], disc_loss.data[0]))

            else:
                            # Discriminator Training
                    # Calculating the discriminator loss which is the negative of adversarial loss and no content loss
                disc_loss = torch.mean(torch.log(dis_output))
                
                discrimloss.append(disc_loss.data[0])

                optimizer_disc.zero_grad()
                disc_loss.backward()
                optimizer_disc.step()

                if batch_idx % args.log_interval == 0:
                    print('Train Epoch: {} [{}/{} ({:.0f}%)]\tDiscriminator Loss: {:.6f}'.format(
                    epoch, batch_idx * len(image), len(trainloader.dataset),
                    100. * batch_idx / len(trainloader), disc_loss.data[0])) 
        

        
        


for epoch in range(1, args.epochs+1):

    # if epoch <= 15:
 #        adjust_learning_rate(optimizer_gen, epoch)        
 #    else:
 #      adjust_learning_rate(optimizer_gen, epoch)
 #      adjust_learning_rate(optimizer_disc,epoch-15)
    train(epoch)
    if epoch == args.epochs_gen:
        torch.save(g_net,'../gen_model_mid.pt')
        torch.save(d_net,'../disc_model_mid.pt')


    # if iter%args.log_interval == 0:        
    #     test()

torch.save(g_net,'../gen_model_final.pt')
torch.save(d_net,'../disc_model_final.pt')

np.save('../ContentLoss.npy',contentloss)
np.save('../DiscriminatorLoss.npy',discrimloss)

# g_net = torch.load('gen_model.pt')
# d_net = torch.load('disc_model.pt')
