; ==============================================================================
; DATA.INC - Static Dataset and Variables for Single Perceptron
; ==============================================================================

NUM_SAMPLES EQU 10

; Training Dataset (10 static samples: X1, X2 features and binary target Y)
x1_data     DW 0, 0, 1, 0, 1, 2, 3, 2, 3, 4
x2_data     DW 0, 1, 0, 1, 1, 2, 2, 3, 3, 4
y_data      DW 0, 0, 0, 0, 0, 1, 1, 1, 1, 1

; Hyperparameters & Model Weights
lr          DW 1            ; Learning rate (eta = 1)
epochs      DW 20           ; Maximum training epochs
w1          DW 0            ; Weight 1
w2          DW 0            ; Weight 2
bias        DW 0            ; Bias

; Runtime Working Variables
cur_x1      DW 0            ; Current input X1
cur_x2      DW 0            ; Current input X2
cur_y       DW 0            ; Current target Y
pred_y      DW 0            ; Predicted class (0 or 1)
net_val     DW 0            ; Net linear combination: (w1*x1) + (w2*x2) + bias
delta       DW 0            ; Delta = lr * error
loss        DW 0            ; Epoch misclassifications
epoch       DW 0            ; Epoch counter
idx         DW 0            ; Sample index

; Test Sample for 1 Inference
test_x1     DW 2            ; Test feature X1
test_x2     DW 2            ; Test feature X2
test_y      DW 0            ; Predicted class result
