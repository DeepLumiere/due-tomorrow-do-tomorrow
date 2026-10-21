JUMPS
.MODEL small
.STACK 100h

.DATA
INCLUDE DATA.INC

msg_epochs  DB 'Enter epochs: $'
msg_lr      DB 'Enter lr: $'
msg_epoch   DB 'Epoch: $'
msg_loss    DB ' Loss: $'
msg_w1      DB 'w1: $'
msg_w2      DB 'w2: $'
msg_b       DB 'b: $'
msg_x1      DB 'Enter test x1: $'
msg_x2      DB 'Enter test x2: $'
msg_pred    DB 'Prediction: $'

.CODE

start:
    mov  ax, @data
    mov  ds, ax

    ; 1. Input epochs and lr
    lea  dx, msg_epochs
    mov  ah, 09h
    int  21h
    call read_num
    mov  epochs, ax

    lea  dx, msg_lr
    mov  ah, 09h
    int  21h
    call read_num
    mov  lr, ax

    call print_crlf

    ; 2. Train perceptron (prints each epoch and loss)
    call train

    call print_crlf

    ; 3. Print final results (w1, w2, b)
    lea  dx, msg_w1
    mov  ah, 09h
    int  21h
    mov  ax, w1
    call print_num
    call print_crlf

    lea  dx, msg_w2
    mov  ah, 09h
    int  21h
    mov  ax, w2
    call print_num
    call print_crlf

    lea  dx, msg_b
    mov  ah, 09h
    int  21h
    mov  ax, bias
    call print_num
    call print_crlf

    call print_crlf

    ; 4. User input for test sample
    lea  dx, msg_x1
    mov  ah, 09h
    int  21h
    call read_num
    mov  test_x1, ax

    lea  dx, msg_x2
    mov  ah, 09h
    int  21h
    call read_num
    mov  test_x2, ax

    ; 5. Run inference and display prediction
    call inference

    mov  ax, 4C00h
    int  21h

linear_head PROC
    mov  ax, w1
    imul cur_x1            
    mov  bx, ax

    mov  ax, w2
    imul cur_x2         
    add  bx, ax           

    add  bx, bias           
    mov  ax, bx
    mov  net_val, ax
    ret
linear_head ENDP

classifier PROC
    call linear_head
    cmp  ax, 0
    jge  cl_one
    xor  ax, ax
    ret
cl_one:
    mov  ax, 1
    ret
classifier ENDP

backprop PROC
    mov  ax, cur_y
    sub  ax, pred_y    
    jz   bp_done         

    imul lr              
    mov  delta, ax

    mov  ax, delta
    imul cur_x1
    add  w1, ax

    mov  ax, delta
    imul cur_x2
    add  w2, ax

    mov  ax, delta
    add  bias, ax

bp_done:
    ret
backprop ENDP

train PROC
    mov  w1, 0
    mov  w2, 0
    mov  bias, 0
    mov  epoch, 0

tr_epoch_loop:
    mov  ax, epoch
    cmp  ax, epochs
    jge  tr_done

    mov  loss, 0
    mov  idx, 0

tr_sample_loop:
    mov  ax, idx
    cmp  ax, NUM_SAMPLES
    jge  tr_epoch_end

    mov  si, idx
    shl  si, 1             
    mov  ax, x1_data[si]
    mov  cur_x1, ax
    mov  ax, x2_data[si]
    mov  cur_x2, ax
    mov  ax, y_data[si]
    mov  cur_y, ax

    call classifier
    mov  pred_y, ax

    mov  ax, cur_y
    cmp  ax, pred_y
    je   tr_sample_ok

    inc  loss
    call backprop

tr_sample_ok:
    inc  idx
    jmp  tr_sample_loop

tr_epoch_end:
    ; Display current epoch and loss
    lea  dx, msg_epoch
    mov  ah, 09h
    int  21h

    mov  ax, epoch
    inc  ax
    call print_num

    lea  dx, msg_loss
    mov  ah, 09h
    int  21h

    mov  ax, loss
    call print_num
    call print_crlf

    inc  epoch
    jmp  tr_epoch_loop

tr_done:
    ret
train ENDP

inference PROC
    mov  ax, test_x1
    mov  cur_x1, ax
    mov  ax, test_x2
    mov  cur_x2, ax

    call classifier
    mov  test_y, ax

    lea  dx, msg_pred
    mov  ah, 09h
    int  21h

    mov  ax, test_y
    call print_num
    call print_crlf

    ret
inference ENDP

; ==============================================================================
; Helper I/O Procedures (Simple, no fancy terminal design)
; ==============================================================================

read_num PROC
    push bx
    push cx
    push dx
    push si

    xor  bx, bx
    xor  cx, cx
    xor  si, si

rn_loop:
    mov  ah, 01h
    int  21h
    cmp  al, 0Dh
    je   rn_done
    cmp  al, 0Ah
    je   rn_done
    cmp  al, '-'
    jne  rn_check_digit
    cmp  si, 0
    jne  rn_loop
    mov  cx, 1
    jmp  rn_loop

rn_check_digit:
    cmp  al, '0'
    jb   rn_loop
    cmp  al, '9'
    ja   rn_loop

    sub  al, '0'
    mov  ah, 0
    push ax

    mov  ax, bx
    mov  dx, 10
    imul dx
    mov  bx, ax
    pop  ax
    add  bx, ax
    inc  si
    jmp  rn_loop

rn_done:
    call print_crlf
    mov  ax, bx
    cmp  cx, 1
    jne  rn_exit
    neg  ax

rn_exit:
    pop  si
    pop  dx
    pop  cx
    pop  bx
    ret
read_num ENDP

print_num PROC
    push ax
    push bx
    push cx
    push dx

    cmp  ax, 0
    jge  pn_positive
    push ax
    mov  dl, '-'
    mov  ah, 02h
    int  21h
    pop  ax
    neg  ax

pn_positive:
    xor  cx, cx
    mov  bx, 10

pn_div_loop:
    xor  dx, dx
    div  bx
    push dx
    inc  cx
    cmp  ax, 0
    jne  pn_div_loop

pn_print_loop:
    pop  dx
    add  dl, '0'
    mov  ah, 02h
    int  21h
    loop pn_print_loop

    pop  dx
    pop  cx
    pop  bx
    pop  ax
    ret
print_num ENDP

print_crlf PROC
    push ax
    push dx
    mov  dl, 0Dh
    mov  ah, 02h
    int  21h
    mov  dl, 0Ah
    mov  ah, 02h
    int  21h
    pop  dx
    pop  ax
    ret
print_crlf ENDP

END start